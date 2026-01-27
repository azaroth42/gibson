
import asyncio
import asyncpg
import re
import os
from db import DATABASE_URL

ADVANCES_FILE_PATH = "rules/advances.md"
EQUIPMENT_FILE_PATH = "rules/equipment.md"

# Helper for slug generation
def to_slug(text):
    return re.sub(r'[^a-z0-9_]', '_', text.lower()).strip('_')

async def populate_db(conn, table_nodes="ability_nodes", table_advances="character_advances", 
                      table_items="items", table_char_items="character_items"):
    """
    Parses rules files and populates the database.
    Assumes tables exist.
    """
    print(f"Populating {table_nodes} and {table_items}...")
    
    # --- Part 1: Ability Tree (from rebuild_tree.py) ---
    print(f"Clearing {table_nodes}...")
    # Truncate nodes (cascades to advances)
    await conn.execute(f"TRUNCATE {table_nodes} CASCADE") 

    # We need to handle IDs. To match rebuild_tree logic which uses SERIAL, 
    # we just insert and let DB handle IDs.
    
    # State tracking
    node_keys = {} # id -> slug

    async def insert_node(key, name, description, cost, parent_id):
        base_key = to_slug(key)
        # Unique key generation
        for i in range(100):
             suffix = f"_{i}" if i > 0 else ""
             candidate_key = f"{base_key}{suffix}"
             try:
                 # Use dynamic table name
                 query = f"""
                    INSERT INTO {table_nodes} (key, name, description, cost, parent_id)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING id
                 """
                 return await conn.fetchval(query, candidate_key, name, description, cost, parent_id)
             except asyncpg.UniqueViolationError:
                 continue
        raise Exception(f"Could not generate unique key for {base_key}")

    async def update_desc(nid, lines):
        if not nid or not lines: return
        txt = "\n".join(lines).strip()
        await conn.execute(f"UPDATE {table_nodes} SET description = $1 WHERE id = $2", txt, nid)

    # 1.1 Create Roots
    playbooks_slug = "playbooks"
    playbooks_root = await insert_node(playbooks_slug, "Playbooks", "Character Classes", 0, None)
    node_keys[playbooks_root] = playbooks_slug

    basic_slug = "basic_moves"
    basic_moves_root = await insert_node(basic_slug, "Basic Moves", "Moves available to everyone", 0, None)
    node_keys[basic_moves_root] = basic_slug

    # 1.2 Parse Advances File
    if not os.path.exists(ADVANCES_FILE_PATH):
        print(f"Warning: {ADVANCES_FILE_PATH} not found. Skipping tree population.")
    else:
        print(f"Parsing {ADVANCES_FILE_PATH}...")
        with open(ADVANCES_FILE_PATH, 'r') as f:
            lines = f.readlines()

        current_section = None
        current_playbook_id = None
        active_node_id = None
        current_parent_stack = [] # [(indent, id)]
        desc_buffer = []

        for line in lines:
            line_s = line.strip()
            
            # Section Headers
            if line_s == "# Basic Moves":
                current_section = "Basic Moves"
                await update_desc(active_node_id, desc_buffer)
                active_node_id = None
                desc_buffer = []
                continue
            
            if line_s == "# Playbooks":
                current_section = "Playbooks"
                await update_desc(active_node_id, desc_buffer)
                active_node_id = None
                desc_buffer = []
                continue
                
            # Basic Move Header: ## Move: Name
            if line_s.startswith("## Move:"):
                await update_desc(active_node_id, desc_buffer)
                desc_buffer = []
                raw_name = line_s.replace("## Move:", "").strip()
                curr_slug = f"{basic_slug}_{raw_name}"
                
                active_node_id = await insert_node(curr_slug, raw_name, "", 0, basic_moves_root)
                node_keys[active_node_id] = curr_slug
                current_parent_stack = [(-1, active_node_id)]
                continue

            # Playbook Move Header: ### Move: Name
            if line_s.startswith("### Move:") and current_section == "Playbooks":
                await update_desc(active_node_id, desc_buffer)
                desc_buffer = []
                raw_name = line_s.replace("### Move:", "").strip()
                if current_playbook_id:
                    parent_slug = node_keys[current_playbook_id]
                    curr_slug = f"{parent_slug}_{raw_name}"
                    active_node_id = await insert_node(curr_slug, raw_name, "", 0, current_playbook_id)
                    node_keys[active_node_id] = curr_slug
                    current_parent_stack = [(-1, active_node_id)]
                continue

            # Playbook Header: ## Name
            if line_s.startswith("## ") and current_section == "Playbooks" and "Move:" not in line_s and "Advances:" not in line_s:
                await update_desc(active_node_id, desc_buffer)
                desc_buffer = []
                pb_name = line_s.replace("## ", "").strip()
                curr_slug = f"{playbooks_slug}_{pb_name}"
                current_playbook_id = await insert_node(curr_slug, pb_name, "", 0, playbooks_root)
                node_keys[current_playbook_id] = curr_slug
                active_node_id = current_playbook_id
                current_parent_stack = [(-1, active_node_id)]
                continue

            # Advances Header: ### Advances
            if "### Advances" in line:
                await update_desc(active_node_id, desc_buffer)
                desc_buffer = []
                active_node_id = None
                continue

            # List Item: * [Cost] Key/Name: Desc
            if line.lstrip().startswith("* ["):
                await update_desc(active_node_id, desc_buffer)
                desc_buffer = []
                indent = len(line) - len(line.lstrip())
                
                # Regex for * [cost] key: desc OR * [cost] key
                m = re.match(r'\s*\*\s*\[(\d+)\]\s+(.*)', line)
                if not m: continue
                
                cost = int(m.group(1))
                rest = m.group(2).strip()
                
                name = "Unknown"
                desc_text = ""
                
                # Check for explicit name:desc split
                if ':' in rest:
                    parts = rest.split(':', 1)
                    name = parts[0].strip()
                    desc_text = parts[1].strip()
                else:
                    name = rest # Use whole text as name if no colon
                
                # Manage hierarchy
                while current_parent_stack and current_parent_stack[-1][0] >= indent:
                    current_parent_stack.pop()
                
                if current_parent_stack:
                    parent_id = current_parent_stack[-1][1]
                else:
                    # Should not happen if headers were parsed right, but fallback
                    parent_id = current_playbook_id if current_section == "Playbooks" else basic_moves_root
                    
                # Generate key
                parent_key_slug = node_keys.get(parent_id, "unknown")
                curr_slug = f"{parent_key_slug}_{name}"
                
                new_id = await insert_node(curr_slug, name, desc_text, cost, parent_id)
                node_keys[new_id] = to_slug(curr_slug)
                active_node_id = new_id
                current_parent_stack.append((indent, new_id))
                continue

            # Description Accumulator
            if active_node_id:
                if line_s and not line_s.startswith("#"):
                    desc_buffer.append(line_s)

        await update_desc(active_node_id, desc_buffer)
        print("Ability Tree populated.")


    # --- Part 2: Equipment (from import_equipment.py) ---
    print(f"Clearing {table_items}...")
    await conn.execute(f"TRUNCATE {table_items} CASCADE")

    if not os.path.exists(EQUIPMENT_FILE_PATH):
        print(f"Warning: {EQUIPMENT_FILE_PATH} not found. Skipping equipment.")
    else:
        print(f"Parsing {EQUIPMENT_FILE_PATH}...")
        with open(EQUIPMENT_FILE_PATH, 'r') as f:
            lines = f.readlines()
            
        current_type = 'gear'
        current_stress = False
        current_item = None
        items_to_insert = []

        def commit_item():
            nonlocal current_item
            if current_item:
                current_item['description'] = current_item['description'].strip()
                items_to_insert.append(current_item)
                current_item = None

        for line in lines:
            line = line.strip()
            if not line: continue
            
            # Headers
            if line.startswith('## '):
                header = line[3:].strip().lower()
                if 'cyberware' in header:
                    current_type = 'cyberware'
                elif 'gear' in header:
                    current_type = 'gear'
                    commit_item()
                continue
                
            if line.startswith('### '):
                commit_item()
                header = line[4:].strip().lower()
                if 'stress-causing' in header:
                    current_stress = True
                    current_type = 'cyberware'
                elif 'stress-free' in header:
                    current_stress = False
                    current_type = 'cyberware'
                else:
                    # Generic subsection
                    pass 
                continue
                
            if current_type == 'cyberware':
                if line.startswith('#### '):
                    commit_item()
                    name = line[5:].strip()
                    current_item = {
                        'name': name,
                        'description': '',
                        'tags': [],
                        'type': 'cyberware',
                        'stress': current_stress
                    }
                elif current_item:
                    if line.startswith('* +'):
                        tag = line[3:].strip()
                        current_item['tags'].append(tag)
                    elif line.startswith('*'):
                       # If it's a list item not starting with +, treat as part of desc? 
                       # Or if it's purely a list item, maybe append to decription
                       current_item['description'] += line + "\n"
                    else:
                       current_item['description'] += line + "\n"
            
            elif current_type == 'gear':
                if line.startswith('* '):
                    commit_item()
                    content = line[2:].strip()
                    if content.startswith('+'): continue # subtag
                    
                    if ':' in content:
                        name, desc = content.split(':', 1)
                        name = name.strip()
                        desc = desc.strip()
                    else:
                        name = content
                        desc = ""
                    
                    current_item = {
                        'name': name,
                        'description': desc,
                        'tags': [],
                        'type': 'gear',
                        'stress': False
                    }
                    commit_item() 

        commit_item() # Flush last
        
        print(f"Inserting {len(items_to_insert)} items...")
        for item in items_to_insert:
            await conn.execute(f"""
                INSERT INTO {table_items} (name, description, tags, type, stress)
                VALUES ($1, $2, $3, $4, $5)
            """, item['name'], item['description'], item['tags'], item['type'], item['stress'])
            
    print("Database population complete.")

async def main():
    conn = await asyncpg.connect(DATABASE_URL)
    await populate_db(conn)
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
