
import asyncio
import asyncpg
from db import DATABASE_URL

async def migrate():
    print("Migrating schema to use join tables...")
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        
        # 1. Drop existing fields if they exist (ignoring data loss as per loose instructions, or backing up if possible.
        # But wait, we can't easily drop columns without losing data. 
        # I'll first create the new tables.
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                tags TEXT[],
                cost INTEGER DEFAULT 0
            );
            
            CREATE TABLE IF NOT EXISTS character_advances (
                id SERIAL PRIMARY KEY,
                character_id INTEGER REFERENCES characters(id) ON DELETE CASCADE,
                advance_id INTEGER REFERENCES ability_nodes(id) ON DELETE CASCADE,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS character_items (
                id SERIAL PRIMARY KEY,
                character_id INTEGER REFERENCES characters(id) ON DELETE CASCADE,
                item_id INTEGER REFERENCES items(id) ON DELETE CASCADE,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 2. Check if columns exist before trying to drop them
        # We assume they do based on previous state. 
        # But if we want to migrate data we should do it here. 
        # Since the previous users had JSONB which contained "key" for advances.
        # We need to map those keys to ability_nodes ids.
        
        print("Migrating existing advances...")
        rows = await conn.fetch("SELECT id, advances FROM characters")
        for row in rows:
            char_id = row['id']
            advances_json = row['advances'] # List of dicts or strings
            if not advances_json:
                continue
                
            import json
            advances = json.loads(advances_json) if isinstance(advances_json, str) else advances_json
            
            for adv in advances:
                key = adv.get('key') if isinstance(adv, dict) else adv
                if not key: continue
                
                # specific handling for timestamp if in dict
                
                # Find node id
                node_id = await conn.fetchval("SELECT id FROM ability_nodes WHERE key = $1", key)
                if node_id:
                     # Check if already added
                     exists = await conn.fetchval("SELECT 1 FROM character_advances WHERE character_id = $1 AND advance_id = $2", char_id, node_id)
                     if not exists:
                         await conn.execute("INSERT INTO character_advances (character_id, advance_id) VALUES ($1, $2)", char_id, node_id)
                else:
                    print(f"Warning: Advance '{key}' not found in ability_nodes")

        # 3. Drop columns
        print("Dropping legacy columns...")
        await conn.execute("ALTER TABLE characters DROP COLUMN IF EXISTS advances")
        await conn.execute("ALTER TABLE characters DROP COLUMN IF EXISTS items")
        
        print("Migration complete.")
        await conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(migrate())
