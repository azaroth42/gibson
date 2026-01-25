
import asyncio
import asyncpg
from db import DATABASE_URL

async def debug_db():
    conn = await asyncpg.connect(DATABASE_URL)
    
    print("--- Ability Nodes (First 20) ---")
    rows = await conn.fetch("SELECT id, name, parent_id FROM ability_nodes LIMIT 20")
    for r in rows:
        print(dict(r))
        
    print("\n--- Playbooks Root Children ---")
    pb_root = await conn.fetchrow("SELECT id FROM ability_nodes WHERE name = 'Playbooks'")
    if pb_root:
        rows = await conn.fetch("SELECT id, name FROM ability_nodes WHERE parent_id = $1", pb_root['id'])
        for r in rows:
            print(dict(r))
            
    print("\n--- Basic Moves Root Children ---")
    bm_root = await conn.fetchrow("SELECT id FROM ability_nodes WHERE name = 'Basic Moves'")
    if bm_root:
        rows = await conn.fetch("SELECT id, name FROM ability_nodes WHERE parent_id = $1", bm_root['id'])
        for r in rows:
            print(dict(r))

    print("\n--- Character Advances ---")
    rows = await conn.fetch("""
        SELECT c.name as char_name, an.name as advance_name 
        FROM character_advances ca
        JOIN characters c ON ca.character_id = c.id
        JOIN ability_nodes an ON ca.advance_id = an.id
        LIMIT 20
    """)
    for r in rows:
        print(f"{r['char_name']}: {r['advance_name']}")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(debug_db())
