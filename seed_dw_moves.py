import asyncio
import re
from db import init_db, get_db_pool

RULES_FILE = 'DungeonWorld_Rules.md'

async def seed_moves():
    print("Initializing database...")
    await init_db()
    
    pool = await get_db_pool()
    
    print(f"Reading rules from {RULES_FILE}...")
    try:
        with open(RULES_FILE, 'r') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error: {RULES_FILE} not found.")
        return

    moves = []
    
    current_class = "Basic"
    current_category = "Basic Moves" # Basic Moves, Starting Moves, Advanced Moves
    
    # Regex patterns
    class_header_re = re.compile(r'^# THE (.*)$')
    section_header_re = re.compile(r'^## (.*)$')
    move_header_re = re.compile(r'^### (.*)$')
    
    # Buffer for collecting description text
    current_move_name = None
    current_move_desc_lines = []
    
    def flush_move():
        nonlocal current_move_name, current_move_desc_lines
        if current_move_name:
            description = "\n".join(current_move_desc_lines).strip()
            # Clean up checklist markers if any
            description = description.replace('* [ ] ', '- ')
            
            # Determine type
            move_type = 'basic'
            if current_class != "Basic":
                if "Starting" in current_category:
                    move_type = 'starting'
                elif "Advanced" in current_category:
                    move_type = 'advanced'
            
            moves.append({
                'name': current_move_name,
                'description': description,
                'class': current_class if current_class != "Basic" else None,
                'type': move_type
            })
            # print(f"Found move: {current_move_name} ({current_class} - {move_type})")
        
        current_move_name = None
        current_move_desc_lines = []

    for line in lines:
        line = line.strip()
        if not line:
            if current_move_name:
                current_move_desc_lines.append("")
            continue
            
        # Check for headers
        class_match = class_header_re.match(line)
        if class_match:
            flush_move()
            current_class = class_match.group(1).title() # "BARD" -> "Bard"
            # Special case for "The Bard" -> keep "The Bard" format if desired, 
            # or strictly "Bard". Previous code used "The Bard". 
            # The header is "THE BARD", so group(1) is "BARD".
            # Let's clean it.
            if current_class == "The Bard": current_class = "The Bard" # It's title cased above
            else: current_class = "The " + current_class # Unified "The ClassName"
            
            current_category = "Starting Moves" # Default content start
            continue
            
        section_match = section_header_re.match(line)
        if section_match:
            flush_move()
            current_category = section_match.group(1)
            continue
            
        move_match = move_header_re.match(line)
        if move_match:
            flush_move()
            current_move_name = move_match.group(1).strip()
            # Remove (Stat) from name if present e.g. "Hack and Slash (Str)"
            current_move_name = re.sub(r'\s*\(\w+\)$', '', current_move_name)
            continue
            
        # Parse list-item moves (Advanced Moves usually)
        # * **[ ] Move Name:** Description
        list_move_match = re.search(r'^\* \*\*\[ \] (.*?):\*\*(.*)', line)
        if list_move_match:
            flush_move()
            current_move_name = list_move_match.group(1).strip()
            desc_start = list_move_match.group(2).strip()
            current_move_desc_lines = [desc_start]
            continue
            
        # Collect description
        if current_move_name:
            current_move_desc_lines.append(line)

    flush_move() # Flush last move
    
    print(f"Parsed {len(moves)} moves.")
    
    async with pool.acquire() as conn:
        # Create tables if not exist (using db schema call would be safer but let's assume existence or run raw)
        # We rely on schema.sql having been applied or app being initialized.
        # Let's run the schema snippet for the new table just in case?
        # No, let's assume the user/previous step applied it.
        # Schema is already managed by init_db (schema.sql), so we don't strictly need CREATE TABLE here.
        # But for robustness, let's assume it exists or init_db handled it.
        
        # Clear existing
        await conn.execute("DELETE FROM dw_reference_moves")
        
        for m in moves:
            print(f"Adding: {m['name']} ({m['class'] or 'Basic'})")
            await conn.execute("""
                INSERT INTO dw_reference_moves (class, name, description, type)
                VALUES ($1, $2, $3, $4)
            """, m['class'], m['name'], m['description'], m['type'])
            
    print("Done.")

if __name__ == "__main__":
    asyncio.run(seed_moves())
