import asyncio
import asyncpg
import os

DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "gibson")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

async def run():
    print(f"Connecting to {DATABASE_URL}")
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        print("Adding coords to characters...")
        await conn.execute("ALTER TABLE characters ADD COLUMN IF NOT EXISTS x INTEGER DEFAULT NULL")
        await conn.execute("ALTER TABLE characters ADD COLUMN IF NOT EXISTS y INTEGER DEFAULT NULL")
        
        print("Adding coords to countdown_clocks...")
        await conn.execute("ALTER TABLE countdown_clocks ADD COLUMN IF NOT EXISTS x INTEGER DEFAULT NULL")
        await conn.execute("ALTER TABLE countdown_clocks ADD COLUMN IF NOT EXISTS y INTEGER DEFAULT NULL")
        
        print("Done.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(run())
