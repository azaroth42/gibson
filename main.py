from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import List
import json
import os
import re
from contextlib import asynccontextmanager
from hypercorn.asyncio import serve
from hypercorn.config import Config
import asyncio

from db import init_db, get_db_pool

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    app.state.pool = await get_db_pool()
    yield
    # Shutdown
    await app.state.pool.close()

app = FastAPI(lifespan=lifespan)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="static")

from models import Character, CharacterCreate, CharacterUpdate

@app.get("/tree")
async def get_ability_tree():
    with open("ability-tree.json", "r") as f:
        return json.load(f)

@app.post("/characters", response_model=Character)
async def create_character(char: CharacterCreate):
    pool = app.state.pool
    async with pool.acquire() as conn:
        # Initial stats/setup based on playbook could happen here, but keeping it simple
        row = await conn.fetchrow(
            "INSERT INTO characters (name, playbook) VALUES ($1, $2) RETURNING *",
            char.name, char.playbook
        )
        return Character(**dict(row))

@app.get("/characters", response_model=List[Character])
async def list_characters():
    pool = app.state.pool
    rows = await pool.fetch("SELECT * FROM characters ORDER BY id DESC")
    return [Character(**dict(row)) for row in rows]

@app.get("/characters/{char_id}", response_model=Character)
async def get_character(char_id: int):
    pool = app.state.pool
    row = await pool.fetchrow("SELECT * FROM characters WHERE id = $1", char_id)
    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Character not found")
    return Character(**dict(row))

@app.put("/characters/{char_id}", response_model=Character)
async def update_character(char_id: int, char_update: CharacterUpdate):
    pool = app.state.pool
    update_data = char_update.model_dump(exclude_unset=True)
    if not update_data:
        # No updates
        return await get_character(char_id)

    set_clauses = []
    values = []
    for i, (key, value) in enumerate(update_data.items(), start=1):
        if key == 'stats' or key == 'advances' or key == 'items':
            # Ensure JSONB compat? asyncpg handles dict to json automatically if type is jsonb?
            # Usually need json.dumps if using text, but asyncpg has codecs.
            # Assuming asyncpg handles it or we pass string. 
            # In schema.sql they are JSONB. asyncpg + PostgreSQL handles python dict -> jsonb usually.
            pass
        set_clauses.append(f"{key} = ${i}")
        values.append(value)
    
    values.append(char_id)
    query = f"UPDATE characters SET {', '.join(set_clauses)} WHERE id = ${len(values)} RETURNING *"
    
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, *values)
        if not row:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Character not found")
        return Character(**dict(row))

@app.websocket("/ws/{char_id}")
async def character_websocket(websocket: WebSocket, char_id: int):
    await websocket.accept()
    pool = app.state.pool
    
    # Verify character exists
    row = await pool.fetchrow("SELECT * FROM characters WHERE id = $1", char_id)
    if not row:
        await websocket.close(code=4004, reason="Character not found")
        return

    try:
        while True:
            data = await websocket.receive_text()
            print(f"Char {char_id} received: {data}")
            
            try:
                message = json.loads(data)
                command_text = message.get("text", "").lower()
            except:
                command_text = data.lower()
                
            response = "Command not recognized"
            updated = False
            
            # Regex Command Parsing
            # 1. Set Stat: "Set [Stat] to [Value]"
            stat_match = re.search(r"set (\w+) to (-?\d+)", command_text)
            if stat_match:
                stat_name = stat_match.group(1)
                value = int(stat_match.group(2))
                
                # Check if it is a main field (health, experience, max_health)
                if stat_name in ["health", "hp"]:
                     await pool.execute("UPDATE characters SET health = $1 WHERE id = $2", value, char_id)
                     response = f"Health set to {value}"
                     updated = True
                elif stat_name in ["xp", "experience"]:
                     await pool.execute("UPDATE characters SET experience = $1 WHERE id = $2", value, char_id)
                     response = f"Experience set to {value}"
                     updated = True
                else:
                    # Assume it's a stat in the 'stats' jsonb
                    # Need to read, update, write? Or use jsonb_set?
                    # Using jsonb_set is more atomic but complex with variables.
                    # easier: read, update, write
                    char_row = await pool.fetchrow("SELECT stats FROM characters WHERE id = $1", char_id)
                    stats = char_row['stats'] or {}
                    stats[stat_name] = value
                    await pool.execute("UPDATE characters SET stats = $1 WHERE id = $2", stats, char_id)
                    response = f"Stat {stat_name} set to {value}"
                    updated = True

            # 2. Damage/Heal: "Take [N] damage", "Heal [N]"
            if "damage" in command_text:
                dmg_match = re.search(r"take (\d+) damage", command_text)
                if dmg_match:
                    amount = int(dmg_match.group(1))
                    await pool.execute("UPDATE characters SET health = health - $1 WHERE id = $2", amount, char_id)
                    response = f"Took {amount} damage"
                    updated = True
            
            if "heal" in command_text:
                heal_match = re.search(r"heal (\d+)", command_text)
                if heal_match:
                    amount = int(heal_match.group(1))
                    await pool.execute("UPDATE characters SET health = health + $1 WHERE id = $2", amount, char_id)
                    response = f"Healed {amount} points"
                    updated = True

            # Send confirmation
            await websocket.send_text(json.dumps({"type": "info", "message": response}))
            
            # If updated, send new character state
            if updated:
                new_row = await pool.fetchrow("SELECT * FROM characters WHERE id = $1", char_id)
                char_data = dict(new_row)
                # json dumps handled by default? no we need to serialize for websocket
                # Character model serialization
                model = Character(**char_data)
                # Use model_dump_json?
                await websocket.send_text(json.dumps({"type": "update", "character": model.model_dump()}))

    except Exception as e:
        print(f"WebSocket Error: {e}")


if __name__ == "__main__":
    config = Config()
    config.bind = ["localhost:8000"]
    asyncio.run(serve(app, config))
