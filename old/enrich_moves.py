
import asyncio
import asyncpg
import re
import os
from db import DATABASE_URL

ADVANCES_FILE_PATH = "advances.md"

async def enrich():
    print("Connecting to DB...")
    conn = await asyncpg.connect(DATABASE_URL)
    
    # helper
    async def upsert_node(key, name, description, cost, parent_id):
        # Check if exists
        row = await conn.fetchrow("SELECT id FROM ability_nodes WHERE key = $1", key)
        if row:
            # Update
            await conn.execute("""
                UPDATE ability_nodes 
                SET name = $1, description = $2, cost = $3, parent_id = $4 
                WHERE id = $5
            """, name, description, cost, parent_id, row['id'])
            return row['id']
        else:
            # Insert
            return await conn.fetchval("""
                INSERT INTO ability_nodes (key, name, description, cost, parent_id)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
            """, key, name, description, cost, parent_id)

    async def update_meta(key, name, description):
        # Update name/desc only, keep pointers
        await conn.execute("UPDATE ability_nodes SET name = $1, description = $2 WHERE key = $3", name, description, key)

    with open(ADVANCES_FILE_PATH, 'r') as f:
        lines = f.readlines()

    current_section = None # 'Basic Moves', 'Playbooks'
    current_playbook = None # node key e.g. 'killer'
    current_playbook_id = None
    
    current_move_key = None # e.g. 'mix-it-up'
    current_move_name = None
    
    buffer = []
    capture_mode = None # 'desc_buffer'

    # Prepare playbooks root
    playbooks_root_id = await conn.fetchval("SELECT id FROM ability_nodes WHERE key = 'playbooks'")
    if not playbooks_root_id:
        playbooks_root_id = await upsert_node('playbooks', 'Playbooks', 'Character Classes', 0, None)
    else:
        await update_meta('playbooks', 'Playbooks', 'Character Classes')

    async def flush_description():
        nonlocal buffer, current_move_key, current_playbook
        desc = "\n".join([b.strip() for b in buffer if b.strip()]).strip()
        buffer = []
        
        if capture_mode == 'move_desc' and current_move_key:
             # Update basic move description
             # Basic moves key is usually the slug of name
             print(f"Updating Move {current_move_key}: {desc[:30]}...")
             await update_meta(current_move_key, current_move_name, desc)
             
        elif capture_mode == 'playbook_desc' and current_playbook:
             # Determine name. Usually "Killer".
             name = current_playbook.title()
             print(f"Updating Playbook {current_playbook}: {desc[:30]}...")
             await update_meta(current_playbook, name, desc)
             
        elif capture_mode == 'intrinsic_move_desc' and current_playbook:
              # This is e.g. Total Badass
              # current_move_key held the slug
              print(f"Upserting Playbook Move {current_move_key}: {desc[:30]}...")
              # Ensure parent is playbook
              pb_id = await conn.fetchval("SELECT id FROM ability_nodes WHERE key = $1", current_playbook)
              await upsert_node(current_move_key, current_move_name, desc, 0, pb_id)

    for line in lines:
        line = line.strip()
        
        if line.startswith("# Basic Moves"):
            current_section = 'Basic Moves'
            await flush_description()
            capture_mode = None
            continue
            
        elif line.startswith("# Playbooks"):
            current_section = 'Playbooks'
            await flush_description()
            capture_mode = None
            continue
            
        # Level 2 Header: ## Move: Mix It Up   OR   ## Killer
        if line.startswith("## "):
            await flush_description()
            header = line[3:].strip()
            
            if "Move:" in header:
                # ## Move: Name
                move_name = header.split("Move:")[1].strip()
                move_key = move_name.lower().replace(" ", "-").replace("'", "")
                
                if current_section == 'Basic Moves':
                     current_move_key = move_key
                     current_move_name = move_name
                     capture_mode = 'move_desc' # wait for ### Description
                     
                     # Ensure basic move exists (it should)
                     # But we set name here? No, description comes later.
                     # However, advances might be inline or later.
                     
                elif current_section == 'Playbooks':
                     # This is an Intrinsic Move like ## Move: Total Badass
                     # It belongs to current_playbook
                     current_move_key = move_key
                     current_move_name = move_name
                     capture_mode = 'intrinsic_move_wait' # wait for desc
                     
            else:
                # ## PlaybookName
                if current_section == 'Playbooks':
                    pb_name = header
                    pb_key = pb_name.lower().replace(" ", "-")
                    current_playbook = pb_key
                    # Ensure playbook node exists
                    pbid = await upsert_node(pb_key, pb_name, "", 0, playbooks_root_id)
                    current_playbook_id = pbid
                    capture_mode = 'playbook_desc_wait'

            continue

        if line.startswith("### Description:"):
            if capture_mode == 'playbook_desc_wait':
                capture_mode = 'playbook_desc'
            elif capture_mode == 'intrinsic_move_wait':
                capture_mode = 'intrinsic_move_desc'
            else:
                capture_mode = 'move_desc'
            buffer = []
            continue

        if line.startswith("### Advances"):
            await flush_description()
            capture_mode = 'advances'
            continue
            
        if line.startswith("### Move Details"):
             await flush_description()
             capture_mode = None
             continue

        # Level 3 Header: ### Move: Total Badass (Inside Playbook)
        if line.startswith("### Move: "):
            await flush_description()
            header = line[9:].strip() # remove "### Move: "
            
            # This is an Intrinsic Move like ### Move: Total Badass
            if current_section == 'Playbooks' and current_playbook:
                 move_name = header
                 move_key = move_name.lower().replace(" ", "-").replace("'", "")
                 
                 current_move_key = move_key
                 current_move_name = move_name
                 capture_mode = 'intrinsic_move_wait' 
                 # We need to capture descriptions next
            continue
             
        # Content Parsing
        if capture_mode in ['move_desc', 'playbook_desc', 'intrinsic_move_desc']:
            if line:
                buffer.append(line)
        
        elif capture_mode == 'intrinsic_move_wait' and line and not line.startswith("#"):
             # Implicit description start
             capture_mode = 'intrinsic_move_desc'
             buffer.append(line)
             
        elif capture_mode == 'advances':
            # Parse advances list
            # * [1] damage1: Base damage is d6+1
            m = re.match(r'\*\s*\[(\d+)\]\s+([^:]+):(.*)', line)
            if m:
                cost = int(m.group(1))
                key = m.group(2).strip()
                rest = m.group(3).strip()
                
                # Heuristic for Name vs Desc
                # Check for second colon: "Sweet Ride: If your..."
                if ':' in rest:
                    parts = rest.split(':', 1)
                    name = parts[0].strip()
                    desc = parts[1].strip()
                else:
                    # No colon, use Key as name (Formatted)? Or the whole text as desc?
                    # User wants Names. "damage1" is not a good name.
                    # If key is "damage1", maybe name is "Damage +1"? 
                    # Let's try to map keys or just capitalize.
                    # Or use the first few words?
                    # "Base damage is d6+1"
                    name = format_key(key)
                    desc = rest
                
                # Update DB
                print(f"Updating Advance {key}: Name='{name}'")
                await update_meta(key, name, desc)

    await flush_description()
    print("Enrichment complete.")
    await conn.close()
    
def format_key(k):
    # damage1 -> Damage 1
    # mix-it-up -> Mix It Up
    s = k.replace("-", " ")
    # split numbers? damage1 -> damage 1
    s = re.sub(r'(\d+)', r' \1', s)
    return s.title().strip()

if __name__ == "__main__":
    asyncio.run(enrich())
