import asyncio
import re
from db import init_db, get_db_pool

RULES_FILE = 'DungeonWorld_Rules.md'

async def seed_items():
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

    # Regex to capture content in parens as tags
    # Example: "Dungeon rations (5 uses, 1 weight)" -> name="Dungeon rations", tags="5 uses, 1 weight"
    # But user said "Worn bow (near, 2 weight), bundle of arrows ..." might be on same line.
    
    # Strategy:
    # 1. Detect "## Gear" section.
    # 2. Iterate lines.
    # 3. If line starts with *, it's an item list.
    # 4. Remove "* [ ] " or "* ".
    # 5. Split by ", " ONLY if it separates distinct items? No, user said "Worn bow (..), bundle of arrows ...".
    #    So splitting by " and " or ", " might be tricky if tags contain commas.
    #    "Worn bow (near, 2 weight), bundle of arrows" -> Split by ", " confusing?
    #    User example: "Worn bow (near, 2 weight), bundle of arrows"
    #    Wait, are they separated by commas or " and "?
    #    Line 651: "* [ ] Chainmail (1 armor, 1 weight) and adventuring gear (1 weight)"
    #    Line 894: "* [ ] Adventuring gear (1 weight) and bundle of arrows (3 ammo, 1 weight)"
    #    It seems " and " is the common separator for distinct items on one choice line.
    #    Also "," might be used?
    #    Let's split by " and " first.
    #    Then check for ","?
    
    items_to_add = []
    
    current_class = None
    in_gear_section = False
    
    class_header_re = re.compile(r'^# THE (.*)$')
    section_header_re = re.compile(r'^## (.*)$')
    
    for line in lines:
        line = line.strip()
        if not line: continue
        
        # Check Class
        class_match = class_header_re.match(line)
        if class_match:
            current_class = class_match.group(1).title()
            in_gear_section = False
            continue
            
        # Check Section
        section_match = section_header_re.match(line)
        if section_match:
            section_name = section_match.group(1).strip()
            if section_name == "Gear":
                in_gear_section = True
            else:
                in_gear_section = False
            continue
            
        if in_gear_section and line.startswith('*'):
            # It's an item line
            # Remove bullet and choice box
            clean_line = re.sub(r'^\* (\[ \] )?', '', line)
            
            # Split by " and " (often used to join items)
            # E.g. "Item A (tags) and Item B (tags)"
            # What about Oxford comma? "Item A, Item B, and Item C"?
            # Let's try to split by " and " first.
            parts = clean_line.split(' and ')
            
            potential_items = []
            for p in parts:
                # Further split by comma if it looks like a list of items?
                # "Dungeon rations (5 uses, 1 weight)" -> tags inside parens have commas.
                # "Item A, Item B" -> simple commas?
                # User example: "Worn bow (near, 2 weight), bundle of arrows"
                # This suggests comma separation outside parens.
                
                # Regex to split by comma NOT inside parens?
                # Or just parse manually.
                
                # Let's process the string `p`.
                # We want to split by ',' but ignore ',' inside '()'.
                
                buffer = ""
                depth = 0
                for char in p:
                    if char == '(': depth += 1
                    elif char == ')': depth -= 1
                    
                    if char == ',' and depth == 0:
                        # Split here
                        if buffer.strip():
                            potential_items.append(buffer.strip())
                        buffer = ""
                    else:
                        buffer += char
                if buffer.strip():
                    potential_items.append(buffer.strip())
            
            for item_str in potential_items:
                # Parse Name and Tags
                # "Name (tags)"
                match = re.match(r'^(.*?)\s*\((.*?)\)$', item_str)
                if match:
                    name = match.group(1).strip()
                    tags_str = match.group(2).strip()
                    tags = [t.strip() for t in tags_str.split(',')]
                else:
                    name = item_str.strip()
                    tags = []
                    
                # Skip if empty or just "choose one:" text
                if name.lower().startswith("choose"): continue
                
                # Calculate weight if present in tags?
                # Schema might have weight? Or just tags.
                # Schema `dw_items`: name, description, tags, weight?, value?
                # Let's check schema first. Assuming `dw_items` matches `items` structure roughly.
                # User said "Add all items into the dw_items table".
                
                items_to_add.append({
                    'name': name,
                    'tags': tags,
                    'class': current_class
                })

    # Insert into DB
    async with pool.acquire() as conn:
        for item in items_to_add:
            print(f"Adding Item: {item['name']} ({item['class']})")
            # Upsert?
            # Table `dw_items` (name, description, tags, weight, value, damage, armor)?
            # Need to verify table columns.
            # Assuming `dw_items` has `name`, `tags`.
            # Extract weight from tags?
            
            weight = 0
            new_tags = []
            for t in item['tags']:
                w_match = re.match(r'(\d+)\s*weight', t)
                if w_match:
                    weight = int(w_match.group(1))
                new_tags.append(t)
            
            # Check schema columns in main.
            # If `dw_items` is simple, we might just use tags.
            
            await conn.execute("""
                INSERT INTO dw_reference_items (name, tags, weight, class)
                VALUES ($1, $2, $3, $4)
            """, item['name'], new_tags, weight, item['class'])
            
    print("Done.")

if __name__ == "__main__":
    asyncio.run(seed_items())
