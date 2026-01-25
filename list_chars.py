
import asyncio
import asyncpg
from db import DATABASE_URL

async def list_chars():
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("SELECT id, name FROM characters")
    print("--- Characters ---")
    for r in rows:
        print(f"ID: {r['id']}, Name: {r['name']}")
    await conn.close()
    
if __name__ == "__main__":
    asyncio.run(list_chars())
