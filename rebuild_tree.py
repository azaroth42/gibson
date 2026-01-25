
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
    
    # Recreate table (using schema from file would be better but simple here)
    await conn.execute("""
        CREATE TABLE ability_nodes (
            id SERIAL PRIMARY KEY,
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

    async def insert_node(name, description, cost, parent_id):
        return await conn.fetchval("""
            INSERT INTO ability_nodes (name, description, cost, parent_id)
            VALUES ($1, $2, $3, $4)
            RETURNING id
        """, name, description, cost, parent_id)

    # 1. Create Playbooks Root
    playbooks_root = await insert_node("Playbooks", "Character Classes", 0, None)

    # Parsing State
    current_root_id = None # For Playbook or Basic Moves container?
    # Actually, Basic Moves are roots themselves? Or gathered under "Basic Moves"?
    # The current tree UI expects a list of roots.
    # Grouping them under "Basic Moves" node might be cleaner, but existing frontend might need adjustment.
    # Let's group Basic Moves under a "Basic Moves" container.
    
    basic_moves_root = await insert_node("Basic Moves", "Moves available to everyone", 0, None)
    
    current_parent_stack = [] # Stack of (indent_level, node_id)
    
    current_section = None # 'Basic Moves', 'Playbooks'
    current_playbook_id = None
    
    # buffers
    name_buffer = None
    desc_buffer = []

    def flush_desc(node_id):
        nonlocal desc_buffer
        if node_id and desc_buffer:
            desc = "\n".join([l.strip() for l in desc_buffer if l.strip()])
            # Update
            # We can't do sql here easily without async, so we'll do it later?
            # Or make this function async
            pass 

    async def update_desc(nid, lines):
        if not nid or not lines: return
        txt = "\n".join(lines).strip()
        await conn.execute("UPDATE ability_nodes SET description = $1 WHERE id = $2", txt, nid)

    active_node_id = None
    
    with open(ADVANCES_FILE_PATH, 'r') as f:
        lines = f.readlines()

    # Pre-scan parsing is hard. State machine.
    
    mode = 'root' 
    # modes: 
    #   root: scanning for headers
    #   move_desc: inside a move block, reading description
    
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

        # Basic Move Header: ## Move: Mix It Up
        if line_s.startswith("## Move:"):
            await update_desc(active_node_id, desc_buffer)
            desc_buffer = []
            
            raw_name = line_s.replace("## Move:", "").strip()
            if current_section == "Playbooks":
                 if current_playbook_id:
                     active_node_id = await insert_node(raw_name, "", 0, current_playbook_id)
                     # Reset indent stack for advances under this move (indent 0 items are children of this)
                     # We use -1 indent for root? No.
                     # List items start at indent 0 or 2 spaces.
                     # We expect them to be children of active_node_id.
                     # So strict parent is active_node_id.
                     # Any list item with indent X should check stack.
                     # Let's say Move is "root" for advances list.
                     current_parent_stack = [(-1, active_node_id)] 
            else:
                 # Basic Move
                 active_node_id = await insert_node(raw_name, "", 0, basic_moves_root)
                 current_parent_stack = [(-1, active_node_id)]
                 
            continue

        # Playbook Header: ## Killer
        if line_s.startswith("## ") and current_section == "Playbooks" and "Move:" not in line_s and "Advances:" not in line_s:
            await update_desc(active_node_id, desc_buffer)
            desc_buffer = []
            
            pb_name = line_s.replace("## ", "").strip()
            current_playbook_id = await insert_node(pb_name, "", 0, playbooks_root)
            active_node_id = current_playbook_id
            # Playbook advances are children of Playbook?
            # Or usually advances are under "## Advances" section which might not have a Move.
            # But in MD, "## Killer" -> Desc -> "### Move: Total Badass" -> Advances.
            # Wait, some playbooks have advances directly?
            # Looking at file:
            # ## Killer -> Desc -> ### Move: Total Badass -> ### Advances
            # So the advances belong to "Total Badass" (Cost 0 move)?
            # Or do they belong to Killer?
            # "Hold +1 for Total Badass" implies it modifies the move.
            # But standard structure is Move -> Advances.
            # BUT: In "Health" section: "## Advances"
            # In "Basic Moves" -> "## Move: Mix It Up" -> "### Advances".
            
            # So usually Advances belong to the preceding Move.
            # Except maybe for Playbooks which might have advances not tied to a move?
            # "## Infiltrator" -> "### Move: Black Operative" -> "### Advances" (children of Black Op)
            
            # The orphan warnings show "Damage 1" (Mix It Up child) was orphaned.
            # This is because I used `current_parent_stack = [(0, active_node_id)]`
            # And then `indent = len(line) - len(line.lstrip())` for `* [1] ...` is 0.
            # So `while indent (0) >= stack_indent (0): pop`. 
            # So it pops the root!
            # Fix: Give the Move root a lower indent, e.g. -1.
            current_parent_stack = [(-1, active_node_id)]
            continue

        # Advances Header
        if "### Advances" in line:
            await update_desc(active_node_id, desc_buffer)
            desc_buffer = [] # Stop capturing description for the move
            active_node_id = None # Now we are parsing list items
            continue
            
        # List Item (Advance)
        # * [1] Damage 1: Base damage is d6+1
        # Indentation matters
        if line.lstrip().startswith("* ["):
            await update_desc(active_node_id, desc_buffer)
            desc_buffer = []
            
            indent = len(line) - len(line.lstrip())
            
            # Parse content
            # * [cost] Name: Desc
            m = re.match(r'\s*\*\s*\[(\d+)\]\s+([^:]+):(.*)', line)
            
            cost = 0
            name = "Unknown"
            desc_text = ""
            
            if m:
                cost = int(m.group(1))
                name = m.group(2).strip()
                desc_text = m.group(3).strip()
            else:
                # Maybe no description separator?
                # * [2] Extra Hold: +1 hold... (Wait that matches)
                # * [2] Simple Item
                m2 = re.match(r'\s*\*\s*\[(\d+)\]\s+(.*)', line)
                if m2:
                    cost = int(m2.group(1))
                    rest = m2.group(2).strip()
                    # Assume whole thing is name if no colon? Or Name is key?
                    # User said: "The name is after the CP in []s, and followed by a colon."
                    # If followed by colon is mandatory, then my regex 1 is correct.
                    # If there's no colon, maybe it's valid?
                    if ':' in rest:
                         parts = rest.split(':', 1)
                         name = parts[0].strip()
                         desc_text = parts[1].strip()
                    else:
                         name = rest
                         desc_text = ""
            
            # Determine Parent based on indent
            # stack elements: (indent, node_id)
            # Find closest parent with indent < current_indent
            while current_parent_stack and current_parent_stack[-1][0] >= indent:
                current_parent_stack.pop()
                
            if current_parent_stack:
                parent_id = current_parent_stack[-1][1]
            else:
                # Should not happen if we pushed move/playbook root
                parent_id = None
                print(f"Warning: Orphan adance {name}")
                
            new_id = await insert_node(name, desc_text, cost, parent_id)
            active_node_id = new_id # For capturing multi-line desc if any (unlikely for list items but possible)
            
            # Push to stack
            current_parent_stack.append((indent, new_id))
            continue
            
        # Description capture
        if active_node_id:
             if line_s and not line_s.startswith("#"):
                 desc_buffer.append(line_s)

    # Final flush
    await update_desc(active_node_id, desc_buffer)
    print("Rebuild complete.")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(rebuild())
