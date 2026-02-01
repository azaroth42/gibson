
import asyncio
import asyncpg
from db import DATABASE_URL

async def main():
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute("ALTER TABLE dw_characters ADD COLUMN IF NOT EXISTS x INTEGER DEFAULT NULL;")
        await conn.execute("ALTER TABLE dw_characters ADD COLUMN IF NOT EXISTS y INTEGER DEFAULT NULL;")
        print("Added x/y columns to dw_characters.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
