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
    options = []
    
    current_class = "Basic"
    current_category = "Basic Moves" 
    
    # Regex patterns
    class_header_re = re.compile(r'^# THE (.*)$')
    section_header_re = re.compile(r'^## (.*)$')
    move_header_re = re.compile(r'^### (.*)$')
    # Option pattern: * **Name:** Description
    option_re = re.compile(r'^\* \*\*(.*?):\*\* (.*)$')
    
    # Buffer for collecting description text
    current_move_name = None
    current_move_desc_lines = []
    
    def flush_move():
        nonlocal current_move_name, current_move_desc_lines
        if current_move_name:
            description = "\n".join(current_move_desc_lines).strip()
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
                'type': current_type # Use the globally determined type
            })
        
        current_move_name = None
        current_move_desc_lines = []

    current_type = 'basic'

    for line in lines:
        line = line.strip()
        if not line:
            # Append paragraph break if we are inside a move
            if current_move_name:
                current_move_desc_lines.append("")
            continue

        # Class Header
        class_match = class_header_re.match(line)
        if class_match:
            flush_move()
            current_class = f"The {class_match.group(1)}"
            current_category = "Starting Moves" # Default assumption
            current_type = 'starting' # Default for class moves
            continue

        # Section Header (##) matches Categories
        section_match = section_header_re.match(line)
        if section_match:
            flush_move()
            current_category = section_match.group(1).strip()
            
            # Reset type based on section
            if "Basic Moves" in current_category:
                current_type = "basic"
            elif "Special Moves" in current_category:
                current_type = "special"
            elif "Advanced Moves" in current_category:
                current_type = "advanced"
            continue
            
        # If we are in Alignment or Race section, parse options
        if current_category in ["Alignment", "Race"]:
            opt_match = option_re.match(line)
            if opt_match:
                opt_name = opt_match.group(1).strip()
                opt_desc = opt_match.group(2).strip()
                options.append({
                    'class': current_class,
                    'type': current_category.lower(),
                    'name': opt_name,
                    'description': opt_desc
                })
            continue

        # Stats & Vitals parsing
        if current_category == "Stats & Vitals":
            # * **Damage:** d6
            # * **Max HP:** 6 + Constitution
            damage_match = re.match(r'^\* \*\*Damage:\*\* (.*)$', line)
            max_hp_match = re.match(r'^\* \*\*Max HP:\*\* (.*)$', line)
            
            if damage_match:
                options.append({
                    'class': current_class,
                    'type': 'damage_die',
                    'name': 'Damage',
                    'description': damage_match.group(1).strip()
                })
                continue
            
            if max_hp_match:
                options.append({
                    'class': current_class,
                    'type': 'max_hp',
                    'name': 'Max HP',
                    'description': max_hp_match.group(1).strip()
                })
                continue

        # Move Header (###)
        move_match = move_header_re.match(line)
        if move_match:
            flush_move()
            raw_name = move_match.group(1).strip()
            
            # Check for Spell Levels (Headers are ###)
            # Rotes, Cantrips, First Level -> starting
            # Other Level Spells -> advanced
            if any(k in raw_name for k in ["Cantrips", "Rotes", "First Level Spells"]):
                current_type = 'starting'
            elif "Level Spells" in raw_name: # 3rd, 5th, 7th, 9th...
                current_type = 'advanced'
            
            current_move_name = re.sub(r'\s*\(\w+\)$', '', raw_name)
            continue
            
        # Parse list-item moves (Advanced Moves usually)
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

    flush_move() 
    
    print(f"Parsed {len(moves)} moves.")
    print(f"Parsed {len(options)} options.")
    
    async with pool.acquire() as conn:
        # Re-apply schema parts?
        # Just ensure tables exist or we might error on insert if manually dropped.
        # Assuming schema is managed.
        
        await conn.execute("DELETE FROM dw_reference_moves")
        await conn.execute("DELETE FROM dw_character_options")

        for m in moves:
            print(f"Adding Move: {m['name']} ({m['class'] or 'Basic'})")
            await conn.execute("""
                INSERT INTO dw_reference_moves (class, name, description, type)
                VALUES ($1, $2, $3, $4)
            """, m['class'], m['name'], m['description'], m['type'])

        for o in options:
            print(f"Adding Option: {o['name']} ({o['class']} - {o['type']})")
            await conn.execute("""
                INSERT INTO dw_character_options (class, type, name, description)
                VALUES ($1, $2, $3, $4)
            """, o['class'], o['type'], o['name'], o['description'])
            
    print("Done.")

if __name__ == "__main__":
    asyncio.run(seed_moves())
