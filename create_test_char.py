
import asyncio
import asyncpg
from db import DATABASE_URL

async def create_test_char():
    conn = await asyncpg.connect(DATABASE_URL)
    
    print("Creating new character...")
    # Insert char
    row = await conn.fetchrow(
            """INSERT INTO characters (name, playbook, tough, cool, sharp, style, chrome) 
               VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *""",
            "Case2", "Netrunner", 0,0,0,0,0
    )
    char_id = row['id']
    print(f"Created char {char_id}")
    
    # Run logic similar to main.py create_character
    # Grant basic moves
    basic_moves_root = await conn.fetchrow("SELECT id FROM ability_nodes WHERE key = 'basic_moves'")
    target_ids = []
    if basic_moves_root:
         bm_rows = await conn.fetch("SELECT id FROM ability_nodes WHERE parent_id = $1", basic_moves_root['id'])
         target_ids.extend([r['id'] for r in bm_rows])

    # Playbook Moves
    pb_slug = f"playbooks_netrunner"
    pb_node = await conn.fetchrow("SELECT id FROM ability_nodes WHERE key = $1", pb_slug)
    if pb_node:
         intrinsic_rows = await conn.fetch("SELECT id FROM ability_nodes WHERE parent_id = $1 AND cost = 0", pb_node['id'])
         print(f"Found {len(intrinsic_rows)} intrinsic moves for Netrunner")
         target_ids.extend([r['id'] for r in intrinsic_rows])
         
    if target_ids:
         records = [(char_id, tid) for tid in set(target_ids)] 
         await conn.executemany(
            "INSERT INTO character_advances (character_id, advance_id) VALUES ($1, $2)",
            records
         )
         print(f"Granted {len(records)} advances")
    
    await conn.close()

if __name__ == "__main__":
    asyncio.run(create_test_char())
