import os
import asyncpg
from typing import Optional

DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "gibson")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

import json

async def init_connection(conn):
    await conn.set_type_codec(
        'jsonb',
        encoder=json.dumps,
        decoder=json.loads,
        schema='pg_catalog'
    )

async def get_db_pool():
    return await asyncpg.create_pool(DATABASE_URL, init=init_connection)

async def init_db():
    # Helper to initialize DB from schema.sql
    # First, try to connect to default postgres DB to check if gibson exists
    try:
        sys_conn = await asyncpg.connect(user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT, database='postgres')
        exists = await sys_conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", DB_NAME)
        if not exists:
            # Create DB
            await sys_conn.execute(f'CREATE DATABASE "{DB_NAME}"')
        await sys_conn.close()
    except Exception as e:
        print(f"Warning: Could not check/create database: {e}")
        # Proceeding hoping it exists or is managed externally

    # Now connect to target DB and run schema
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        with open('schema.sql', 'r') as f:
            schema = f.read()
            await conn.execute(schema)
        await conn.close()
        print("Database initialized.")
    except Exception as e:
        print(f"Error initializing database tables: {e}")

