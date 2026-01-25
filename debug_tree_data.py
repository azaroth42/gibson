
import asyncio
import asyncpg
import json
from db import DATABASE_URL

async def debug_data():
    conn = await asyncpg.connect(DATABASE_URL)
    
    print("--- Checking Tree Root ---")
    basic_root = await conn.fetchrow("SELECT id, name, key FROM ability_nodes WHERE key = 'basic_moves'")
    print(f"Basic Moves Root: {dict(basic_root) if basic_root else 'None'}")
    
    if basic_root:
        children = await conn.fetch("SELECT id, name, key FROM ability_nodes WHERE parent_id = $1 LIMIT 5", basic_root['id'])
        print(f"First 5 children: {[dict(r) for r in children]}")
        
    print("\n--- Checking Character Advances ---")
    # Get latest character
    char = await conn.fetchrow("SELECT id, name FROM characters ORDER BY id DESC LIMIT 1")
    if char:
        print(f"Character: {char['name']} (ID: {char['id']})")
        advances = await conn.fetch("SELECT advance_id FROM character_advances WHERE character_id = $1", char['id'])
        print(f"Owned Advance IDs: {[r['advance_id'] for r in advances]}")
    else:
        print("No characters found.")
        
    await conn.close()

if __name__ == "__main__":
    asyncio.run(debug_data())
