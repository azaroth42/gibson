
import asyncio
import asyncpg
from db import DATABASE_URL, get_db_pool

async def debug_api_logic():
    print("Connecting to DB...")
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        print("Fetching IDs...")
        rows = await conn.fetch("SELECT id FROM characters ORDER BY id DESC")
        print(f"Found {len(rows)} characters.")
        
        for row in rows:
            char_id = row['id']
            print(f"Fetching details for Char ID {char_id}...")
            try:
                # Replicating get_character_internal logic
                char_row = await conn.fetchrow("SELECT * FROM characters WHERE id = $1", char_id)
                print(f"  Basic Data: {char_row['name']}")
                
                # Advances
                adv_rows = await conn.fetch("""
                    SELECT an.name, an.description, an.cost, ca.added_at 
                    FROM character_advances ca
                    JOIN ability_nodes an ON ca.advance_id = an.id
                    WHERE ca.character_id = $1
                """, char_id)
                print(f"  Advances: {len(adv_rows)}")
                
                # Links - THIS was the suspect part
                link_rows = await conn.fetch("""
                    SELECT id, target_name, value
                    FROM character_links
                    WHERE character_id = $1
                    ORDER BY id
                """, char_id)
                print(f"  Links: {len(link_rows)}")
                
            except Exception as e:
                print(f"  ERROR for Char {char_id}: {e}")

    await pool.close()

if __name__ == "__main__":
    asyncio.run(debug_api_logic())
