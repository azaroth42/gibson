import asyncio
import asyncpg
import re
from db import get_db_pool

EQUIPMENT_FILE = "equipment.md"

async def main():
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        # 1. Migration
        print("Migrating schema...")
        try:
            await conn.execute("ALTER TABLE character_items ADD COLUMN IF NOT EXISTS name TEXT")
            await conn.execute("ALTER TABLE character_items ADD COLUMN IF NOT EXISTS tags TEXT[]")
            
            # Use information_schema to check for columns to safely DROP/ADD
            cols = await conn.fetch("SELECT column_name FROM information_schema.columns WHERE table_name = 'items'")
            col_names = [r['column_name'] for r in cols]
            
            if 'cost' in col_names:
                await conn.execute("ALTER TABLE items DROP COLUMN cost")
            if 'stress' not in col_names:
                await conn.execute("ALTER TABLE items ADD COLUMN stress BOOLEAN DEFAULT FALSE")
            
        except Exception as e:
            print(f"Migration warning: {e}")

        # 2. Clear Items
        print("Clearing old items...")
        await conn.execute("TRUNCATE items CASCADE")

        # 3. Parse File
        print("Parsing equipment.md...")
        try:
            with open(EQUIPMENT_FILE, 'r') as f:
                lines = f.readlines()
        except FileNotFoundError:
            print(f"Error: {EQUIPMENT_FILE} not found.")
            return

        current_type = 'gear'
        current_stress = False
        current_item = None
        
        items_to_insert = []

        def commit_item():
            nonlocal current_item
            if current_item:
                # Cleanup description
                current_item['description'] = current_item['description'].strip()
                items_to_insert.append(current_item)
                current_item = None

        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Headers
            if line.startswith('## '):
                # Section
                header = line[3:].strip().lower()
                if 'cyberware' in header:
                    current_type = 'cyberware'
                elif 'gear' in header:
                    current_type = 'gear'
                    commit_item()
                continue
            
            if line.startswith('### '):
                # Sub-section
                commit_item()
                header = line[4:].strip().lower()
                if 'stress-causing' in header:
                    current_stress = True
                    current_type = 'cyberware'
                elif 'stress-free' in header:
                    current_stress = False
                    current_type = 'cyberware'
                else:
                    # Gear Categories like "Melee Weapons"
                    # Just treat as gear context
                    current_type = 'gear'
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
                    # Content
                    if line.startswith('* +'):
                        # Tag
                        tag = line[3:].strip() # remove '* +'
                        current_item['tags'].append(tag)
                    elif line.startswith('*'):
                        # List item in description?
                         # Logic check: listing cyberware summary at top of section vs lists inside item
                         # Item lists usually implied tags or parts of desc.
                         # Let's append to description.
                        current_item['description'] += line + "\n"
                    else:
                        current_item['description'] += line + "\n"
            
            elif current_type == 'gear':
                # Gear items are usually "* Name: Desc" or "* Name"
                if line.startswith('* '):
                    commit_item()
                    content = line[2:].strip()
                    if content.startswith('+'):
                        # This matches "* +tag" inside a list of tags (like Vehicle tags)
                        # Ignoring standalone tags in gear section
                        continue

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
                    commit_item() # Gear is single line usually
                else:
                    # Continuation of gear text? usually not in this format
                    pass

        commit_item()

        # 4. Insert
        print(f"Inserting {len(items_to_insert)} items...")
        for item in items_to_insert:
            desc = item['description']
            await conn.execute("""
                INSERT INTO items (name, description, tags, type, stress)
                VALUES ($1, $2, $3, $4, $5)
            """, item['name'], desc, item['tags'], item['type'], item['stress'])
            
    print("Done.")

if __name__ == "__main__":
    asyncio.run(main())
