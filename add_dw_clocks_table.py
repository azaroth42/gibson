
import asyncio
import asyncpg
from db import DATABASE_URL

async def main():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS dw_countdown_clocks (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            filled INTEGER DEFAULT 0,
            x INTEGER DEFAULT NULL,
            y INTEGER DEFAULT NULL
        );
    """)
    print("Table dw_countdown_clocks created or already exists.")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
