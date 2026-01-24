
import asyncio
import asyncpg
from db import DATABASE_URL

async def migrate():
    print("Migrating schema...")
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute("ALTER TABLE items ADD COLUMN IF NOT EXISTS type TEXT DEFAULT 'gear'")
        print("Added type column to items.")
        await conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(migrate())
