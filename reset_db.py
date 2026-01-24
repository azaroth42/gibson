import asyncio
import asyncpg
from db import DATABASE_URL

async def reset():
    print("Connecting to DB...")
    conn = await asyncpg.connect(DATABASE_URL)
    print("Dropping tables...")
    await conn.execute('DROP TABLE IF EXISTS ability_nodes CASCADE')
    await conn.execute('DROP TABLE IF EXISTS characters CASCADE')
    print("Table dropped.")
    
    # Read new schema
    with open('schema.sql', 'r') as f:
        schema = f.read()
        print("Recreating table...")
        await conn.execute(schema)
    
    await conn.close()
    print("Done.")

if __name__ == "__main__":
    asyncio.run(reset())
