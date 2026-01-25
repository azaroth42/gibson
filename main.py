from fastapi import FastAPI, WebSocket, Request, HTTPException, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
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

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

from models import Character, CharacterCreate, CharacterUpdate

@app.post("/characters", response_model=Character)
async def create_character(char: CharacterCreate):
    pool = app.state.pool
    import random
    stats_vals = [2, 1, 1, 0, -1]
    random.shuffle(stats_vals)
    tough, cool, sharp, style, chrome = stats_vals
    
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO characters (name, playbook, tough, cool, sharp, style, chrome) 
               VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *""",
            char.name, char.playbook, tough, cool, sharp, style, chrome
        )
        
        # Grant free (0 CP) advances
        # ONLY grant basic moves and the specific playbook move
        # Basic moves names:
        basic_moves = [
            'Mix It Up', 'Fight Another Day', 'Act Under Pressure', 'First Aid', 
            'Research', 'Assess', 'Fast Talk', 'Hit the Streets', 'Assist', 'Stressed Out'
        ]
        
        # Add playbook move - need to find move associated with playbook
        # We can look up the Playbook node by name, then find 0 cost children of that playbook node?
        # Or simplistic name matching if names are standard.
        # But Playbook names are capitalization sensitive in DB?
        # Let's just grant basic moves for now, matching on names.
        
        target_names = basic_moves
        # + Playbook Intrinsics? "Total Badass" etc. 
        # Hard to map dynamic playbook name to move name without a lookup or strict naming.
        # But we can find the Playbook node, and grab its 0-cost children?
        
        # Let's try finding the Playbook node
        pb_node = await conn.fetchrow("SELECT id FROM ability_nodes WHERE name = $1", char.playbook)
        if pb_node:
             # Find children of playbook with cost 0 (intrinsic moves)
             intrinsic_rows = await conn.fetch("SELECT id FROM ability_nodes WHERE parent_id = $1 AND cost = 0", pb_node['id'])
             target_ids = [r['id'] for r in intrinsic_rows]
             
             # Also add basic moves
             # Basic Moves are under a "Basic Moves" container?
             # Or just by name.
             bm_rows = await conn.fetch("SELECT id FROM ability_nodes WHERE name = ANY($1)", basic_moves)
             target_ids.extend([r['id'] for r in bm_rows])
             
             if target_ids:
                 # Batch insert
                 records = [(row['id'], tid) for tid in set(target_ids)] # dedup just in case
                 await conn.executemany(
                    "INSERT INTO character_advances (character_id, advance_id) VALUES ($1, $2)",
                    records
                 )

        return await get_character_internal(conn, row['id'])

@app.get("/characters", response_model=List[Character])
async def list_characters():
    pool = app.state.pool
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id FROM characters ORDER BY id DESC")
        chars = []
        for row in rows:
            chars.append(await get_character_internal(conn, row['id']))
        return chars

@app.get("/characters/{char_id}", response_model=Character)
async def get_character(char_id: int):
    pool = app.state.pool
    async with pool.acquire() as conn:
        return await get_character_internal(conn, char_id)

@app.delete("/characters/{char_id}", status_code=204)
async def delete_character(char_id: int):
    pool = app.state.pool
    result = await pool.execute("DELETE FROM characters WHERE id = $1", char_id)
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Character not found")
    return None

@app.put("/characters/{char_id}", response_model=Character)
async def update_character(char_id: int, char_update: CharacterUpdate):
    pool = app.state.pool
    update_data = char_update.model_dump(exclude_unset=True)
    if not update_data:
        return await get_character(char_id)

    set_clauses = []
    values = []
    
    # Remove complex fields from direct update
    complex_fields = ['advances', 'items', 'links']
    for field in complex_fields:
        if field in update_data:
            del update_data[field]
            
    if not update_data:
         return await get_character(char_id)

    for i, (key, value) in enumerate(update_data.items(), start=1):
        set_clauses.append(f"{key} = ${i}")
        values.append(value)
    
    values.append(char_id)
    query = f"UPDATE characters SET {', '.join(set_clauses)} WHERE id = ${len(values)} RETURNING *"
    
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, *values)
        if not row:
            raise HTTPException(status_code=404, detail="Character not found")
        return await get_character_internal(conn, char_id)

class AdvanceAdd(BaseModel):
    name: str # was key
    cost: int

# ... (ws handler updates below) ...

@app.websocket("/ws/{char_id}")
async def websocket_endpoint(websocket: WebSocket, char_id: int):
    await websocket.accept()
    pool = app.state.pool
    try:
        while True:
            message = await websocket.receive_json()
            response = ""
            updated = False
            
            # Check for structured action or text command
            if message.get("type") == "action":
                action = message.get("action")
                if action == "toggle_advance":
                    name = message.get("key") # Frontend sends 'key' as the identifier still? 
                    # I'll update frontend to send 'name' or just treat 'key' field as 'name' content.
                    # Let's assume frontend sends { key: "Mix It Up" } which is the name.
                    
                    # First get the ID for the name
                    node_row = await pool.fetchrow("SELECT id FROM ability_nodes WHERE name = $1", name)
                    if not node_row:
                        response = f"Error: Advance {name} not found"
                    else:
                        node_id = node_row['id']
                        exists_row = await pool.fetchrow(
                            "SELECT id FROM character_advances WHERE character_id = $1 AND advance_id = $2", 
                            char_id, node_id
                        )
                        
                        if exists_row:
                            # Remove
                            await pool.execute(
                                "DELETE FROM character_advances WHERE id = $1", 
                                exists_row['id']
                            )
                            response = f"Removed advance: {name}"
                        else:
                            # Add
                            await pool.execute(
                                "INSERT INTO character_advances (character_id, advance_id) VALUES ($1, $2)", 
                                char_id, node_id
                            )
                            response = f"Added advance: {name}"
                            
                            # Update points used if needed
                            cost = await pool.fetchval("SELECT cost FROM ability_nodes WHERE id = $1", node_id)
                            # Need to acquire connection for transaction or update
                            async with pool.acquire() as conn:
                                await conn.execute("UPDATE characters SET points_used = points_used + $1 WHERE id = $2", cost or 0, char_id)

                        updated = True
            
            if updated:
                async with pool.acquire() as conn:
                    updated_character = await get_character_internal(conn, char_id)
                await websocket.send_json({"response": response, "character": updated_character.model_dump()})
            else:
                await websocket.send_json({"response": response})

    except WebSocketDisconnect:
        print(f"Client #{char_id} disconnected")
    except Exception as e:
        print(f"WebSocket error for client #{char_id}: {e}")
        await websocket.send_json({"error": str(e)})

@app.get("/characters/{char_id}/view-advances", response_class=HTMLResponse)
async def view_advances(request: Request, char_id: int):
    # Verify char exists
    pool = app.state.pool
    row = await pool.fetchrow("SELECT id FROM characters WHERE id = $1", char_id)
    if not row:
        raise HTTPException(status_code=404, detail="Character not found")
    return templates.TemplateResponse("advances.html", {"request": request, "char_id": char_id})

@app.get("/api/tree")
async def get_tree_api():
    pool = app.state.pool
    rows = await pool.fetch("SELECT * FROM ability_nodes ORDER BY id")
    
    nodes_by_id = {}
    roots = []
    
    # First pass: create nodes
    for row in rows:
        node = dict(row)
        node['children'] = []
        nodes_by_id[node['id']] = node
        
    # Second pass: assemble hierarchy
    for row in rows:
        node = nodes_by_id[row['id']]
        if row['parent_id'] is None:
            roots.append(node)
        else:
            parent = nodes_by_id.get(row['parent_id'])
            if parent:
                parent['children'].append(node)
                
    return roots
@app.post("/characters/{char_id}/advances", response_model=Character)
async def add_character_advance(char_id: int, advance: AdvanceAdd):
    pool = app.state.pool
    
    async with pool.acquire() as conn:
        # Check character exists
        char_exists = await conn.fetchval("SELECT 1 FROM characters WHERE id = $1", char_id)
        if not char_exists:
            raise HTTPException(status_code=404, detail="Character not found")

        # Get node info
        node = await conn.fetchrow("SELECT id, parent_id, cost FROM ability_nodes WHERE name = $1", advance.name)
        if not node:
             raise HTTPException(status_code=400, detail=f"Advance '{advance.name}' not found in tree")
        
        node_id = node['id']
        parent_id = node['parent_id']
             
        # Check if already owned
        exists = await conn.fetchval(
            "SELECT 1 FROM character_advances WHERE character_id = $1 AND advance_id = $2", 
            char_id, node_id
        )
        
        if exists:
             return await get_character_internal(conn, char_id)
        
        # Check parent requirement
        if parent_id is not None:
             # Check if parent is ROOT (Playbooks or Basic Moves)
             parent_node = await conn.fetchrow("SELECT name, parent_id FROM ability_nodes WHERE id = $1", parent_id)
             if parent_node and parent_node['parent_id'] is not None: 
                  # Only enforce if parent is not a root Category
                  # "Mix It Up" has parent "Basic Moves" (root). We don't "buy" Basic Moves root.
                  # "Basic Moves" has parent None.
                  parent_owned = await conn.fetchval(
                      "SELECT 1 FROM character_advances WHERE character_id = $1 AND advance_id = $2",
                      char_id, parent_id
                  )
                  # If parent is a container (0 cost?) we might skip check?
                  # But usually we must own the Move to buy its advances.
                  # Basic Moves are owned by default.
                  if not parent_owned:
                      raise HTTPException(status_code=400, detail=f"Parent advance '{parent_node['name']}' must be purchased first.")
             
        # Add advance
        await conn.execute(
            "INSERT INTO character_advances (character_id, advance_id) VALUES ($1, $2)",
            char_id, node_id
        )
        
        # Update points
        await conn.execute("UPDATE characters SET points_used = points_used + $1 WHERE id = $2", node['cost'], char_id)
        
        return await get_character_internal(conn, char_id)

async def get_character_internal(conn, char_id: int) -> Character:
    # Fetch basic details
    row = await conn.fetchrow("SELECT * FROM characters WHERE id = $1", char_id)
    if not row:
         raise HTTPException(status_code=404, detail="Character not found")
    
    char_data = dict(row)
    
    # Fetch advances
    # Changed an.key to an.name
    adv_rows = await conn.fetch("""
        SELECT an.name, an.description, an.cost, ca.added_at 
        FROM character_advances ca
        JOIN ability_nodes an ON ca.advance_id = an.id
        WHERE ca.character_id = $1
    """, char_id)
    
    char_data['advances'] = [{
        "key": r['name'], # Keeping JSON key as 'key' for frontend compatibility or changing to 'name'? Frontend uses 'key' as prop. Let's map name -> key for now to minimize frontend breakage, OR update frontend. User said "Update sheet.html".
        # Better: use 'name' in JSON and update frontend.
        "name": r['name'],
        "description": r['description'],
        "cost": r['cost'], 
        "timestamp": int(r['added_at'].timestamp())
    } for r in adv_rows]
    
    # Mapping for frontend compatibility if models.py expects 'key' inside Dict?
    # models.py says List[Dict[str, Any]]. So keys are flexible.
    # But sheet.html accesses .key
    # I will inject 'key' = 'name' to keep it somewhat compatible or just handle it.

    # ... items ...

    # Fetch links
    link_rows = await conn.fetch("""
        SELECT id, target_name, value
        FROM character_links
        WHERE character_id = $1
        ORDER BY id
    """, char_id)
    
    char_data['links'] = [dict(r) for r in link_rows]
    
    return Character(**char_data)

if __name__ == "__main__":
    config = Config()
    config.bind = ["localhost:8000"]
    asyncio.run(serve(app, config))
