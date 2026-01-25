
import asyncio
import asyncpg
import re
from db import DATABASE_URL

ADVANCES_FILE_PATH = "advances.md"

async def rebuild():
    print("Rebuilding Ability Tree...")
    conn = await asyncpg.connect(DATABASE_URL)
    
    # Reset table
    await conn.execute("DROP TABLE IF EXISTS character_advances")
    await conn.execute("DROP TABLE IF EXISTS ability_nodes CASCADE")
    
    # Recreate table with Key column
    await conn.execute("""
        CREATE TABLE ability_nodes (
            id SERIAL PRIMARY KEY,
            key TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT,
            cost INTEGER DEFAULT 0,
            parent_id INTEGER REFERENCES ability_nodes(id) ON DELETE CASCADE
        );
    """)
    await conn.execute("""
        CREATE TABLE character_advances (
            id SERIAL PRIMARY KEY,
            character_id INTEGER REFERENCES characters(id) ON DELETE CASCADE,
            advance_id INTEGER REFERENCES ability_nodes(id) ON DELETE CASCADE,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    async def insert_node(key, name, description, cost, parent_id):
        base_key = re.sub(r'[^a-z0-9_]', '_', key.lower()).strip('_')
        # Try inserting, if fail, append counter
        for i in range(100):
             suffix = f"_{i}" if i > 0 else ""
             candidate_key = f"{base_key}{suffix}"
             try:
                 return await conn.fetchval("""
                    INSERT INTO ability_nodes (key, name, description, cost, parent_id)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING id
                 """, candidate_key, name, description, cost, parent_id)
             except asyncpg.UniqueViolationError:
                 continue
        raise Exception(f"Could not generate unique key for {base_key}")

    # State tracking for keys
    node_keys = {} # id -> slug

    # 1. Create Playbooks Root
    playbooks_slug = "playbooks"
    playbooks_root = await insert_node(playbooks_slug, "Playbooks", "Character Classes", 0, None)
    node_keys[playbooks_root] = playbooks_slug

    basic_slug = "basic_moves"
    basic_moves_root = await insert_node(basic_slug, "Basic Moves", "Moves available to everyone", 0, None)
    node_keys[basic_moves_root] = basic_slug
    
    current_parent_stack = [] 
    
    current_section = None 
    current_playbook_id = None
    
    name_buffer = None
    desc_buffer = []

    async def update_desc(nid, lines):
        if not nid or not lines: return
        txt = "\n".join(lines).strip()
        await conn.execute("UPDATE ability_nodes SET description = $1 WHERE id = $2", txt, nid)

    active_node_id = None
    
    with open(ADVANCES_FILE_PATH, 'r') as f:
        lines = f.readlines()
    
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

        # Basic Move Header
        if line_s.startswith("## Move:"):
            await update_desc(active_node_id, desc_buffer)
            desc_buffer = []
            
            raw_name = line_s.replace("## Move:", "").strip()
            
            # Basic Move
            parent_slug = basic_slug
            curr_slug = f"{parent_slug}_{raw_name}"
            
            active_node_id = await insert_node(curr_slug, raw_name, "", 0, basic_moves_root)
            node_keys[active_node_id] = curr_slug
            
            current_parent_stack = [(-1, active_node_id)]
                 
            continue

        # Playbook Child Move Header
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

        # Playbook Header
        if line_s.startswith("## ") and current_section == "Playbooks" and "Move:" not in line_s and "Advances:" not in line_s:
            await update_desc(active_node_id, desc_buffer)
            desc_buffer = []
            
            pb_name = line_s.replace("## ", "").strip()
            
            parent_slug = playbooks_slug
            curr_slug = f"{parent_slug}_{pb_name}"
            
            current_playbook_id = await insert_node(curr_slug, pb_name, "", 0, playbooks_root)
            node_keys[current_playbook_id] = curr_slug
            
            active_node_id = current_playbook_id
            current_parent_stack = [(-1, active_node_id)]
            continue

        # Advances Header
        if "### Advances" in line:
            await update_desc(active_node_id, desc_buffer)
            desc_buffer = [] 
            active_node_id = None 
            continue
            
        # List Item
        if line.lstrip().startswith("* ["):
            await update_desc(active_node_id, desc_buffer)
            desc_buffer = []
            
            indent = len(line) - len(line.lstrip())
            
            m = re.match(r'\s*\*\s*\[(\d+)\]\s+([^:]+):(.*)', line)
            
            cost = 0
            name = "Unknown"
            desc_text = ""
            
            if m:
                cost = int(m.group(1))
                name = m.group(2).strip()
                desc_text = m.group(3).strip()
            else:
                m2 = re.match(r'\s*\*\s*\[(\d+)\]\s+(.*)', line)
                if m2:
                    cost = int(m2.group(1))
                    rest = m2.group(2).strip()
                    if ':' in rest:
                         parts = rest.split(':', 1)
                         name = parts[0].strip()
                         desc_text = parts[1].strip()
                    else:
                         name = rest
                         desc_text = ""
            
            while current_parent_stack and current_parent_stack[-1][0] >= indent:
                current_parent_stack.pop()
                
            if current_parent_stack:
                parent_id = current_parent_stack[-1][1]
            else:
                parent_id = None
                print(f"Warning: Orphan adance {name}")
                
            # Key generation based on parent
            if parent_id in node_keys:
                parent_slug = node_keys[parent_id]
                curr_slug = f"{parent_slug}_{name}"
            else:
                curr_slug = f"orphan_{name}"
                
            new_id = await insert_node(curr_slug, name, desc_text, cost, parent_id)
            node_keys[new_id] = re.sub(r'[^a-z0-9_]', '_', curr_slug.lower()).strip('_')
            
            active_node_id = new_id 
            
            current_parent_stack.append((indent, new_id))
            continue
            
        if active_node_id:
             if line_s and not line_s.startswith("#"):
                 desc_buffer.append(line_s)

    await update_desc(active_node_id, desc_buffer)
    print("Rebuild complete.")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(rebuild())
