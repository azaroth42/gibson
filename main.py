from fastapi import FastAPI, WebSocket, Request, HTTPException, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Optional
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
    app.state.tabletop_connections = []
    yield
    # Shutdown
    await app.state.pool.close()

async def broadcast_tabletop(app, message: dict):
    for connection in app.state.tabletop_connections:
        try:
            await connection.send_json(message)
        except Exception as e:
            print(f"Error broadcasting to tabletop: {e}")

app = FastAPI(lifespan=lifespan)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="static")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

from models import Character, CharacterCreate, CharacterUpdate, ItemAdd, LinkAdd

class Clock(BaseModel):
    id: int
    name: str
    filled: int
    x: Optional[int] = None
    y: Optional[int] = None

class ClockCreate(BaseModel):
    name: str
    filled: int = 0
    x: Optional[int] = None
    y: Optional[int] = None

class ClockUpdate(BaseModel):
    name: Optional[str] = None
    filled: Optional[int] = None
    x: Optional[int] = None
    y: Optional[int] = None

class GameState(BaseModel):
    map_image: Optional[str] = None

class GameStateUpdate(BaseModel):
    map_image: Optional[str] = None

@app.post("/characters", response_model=Character)
async def create_character(char: CharacterCreate):
    pool = app.state.pool
    import random
    # Start all stats at -1 per user request
    tough = cool = sharp = style = chrome = -1
    
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO characters (name, playbook, tough, cool, sharp, style, chrome, health, max_health) 
               VALUES ($1, $2, $3, $4, $5, $6, $7, 25, 25) RETURNING *""",
            char.name, char.playbook, tough, cool, sharp, style, chrome
        )
        
        # Grant free (0 CP) advances
        # ONLY grant basic moves and the specific playbook move
        # We need to find the IDs.
        # Basic Moves are under 'Basic Moves' root.
        basic_moves_root = await conn.fetchrow("SELECT id FROM ability_nodes WHERE key = 'basic_moves'")
        target_ids = []
        
        if basic_moves_root:
             # Get all children of "Basic Moves" node.
             bm_rows = await conn.fetch("SELECT id, key FROM ability_nodes WHERE parent_id = $1", basic_moves_root['id'])
             
             allowed_science = ['Netrunner', 'Driver', 'Tech', 'Juicer', 'Face']
             
             for r in bm_rows:
                 if 'science' in r['key'].lower():
                     if char.playbook in allowed_science:
                         target_ids.append(r['id'])
                 else:
                     target_ids.append(r['id'])

        # Playbook Intrinsic Moves (Cost 0)
        # Find Playbook node by key (slugified name)
        pb_slug = f"playbooks_{char.playbook.lower()}"
        pb_node = await conn.fetchrow("SELECT id FROM ability_nodes WHERE key = $1", pb_slug)
        
        if pb_node:
             target_ids.append(pb_node['id']) # Add the playbook node itself so items under it are unlockable
             # Find children of playbook with cost 0 (intrinsic moves)
             intrinsic_rows = await conn.fetch("SELECT id FROM ability_nodes WHERE parent_id = $1 AND cost = 0", pb_node['id'])
             target_ids.extend([r['id'] for r in intrinsic_rows])
             
        if target_ids:
             records = [(row['id'], tid) for tid in set(target_ids)] 
             await conn.executemany(
                "INSERT INTO character_advances (character_id, advance_id) VALUES ($1, $2)",
                records
             )

        new_char = await get_character_internal(conn, row['id'])
        await broadcast_tabletop(app, {"type": "character_update", "payload": new_char.model_dump()})
        return new_char

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
    async with pool.acquire() as conn:
        row = await conn.fetchrow("DELETE FROM characters WHERE id = $1 RETURNING name", char_id)
        if not row:
            raise HTTPException(status_code=404, detail="Character not found")
            
        # Delete links pointing TO this character
        await conn.execute("DELETE FROM character_links WHERE target_name = $1", row['name'])
        
    await broadcast_tabletop(app, {"type": "character_delete", "payload": {"id": char_id}})
    return None

@app.put("/characters/{char_id}", response_model=Character)
async def update_character(char_id: int, char_update: CharacterUpdate):
    pool = app.state.pool
    update_data = char_update.model_dump(exclude_unset=True)
    if not update_data:
        return await get_character(char_id)

    set_clauses = []
    values = []
    
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
        char = await get_character_internal(conn, char_id)
        
    # Broadcast update
    await broadcast_tabletop(app, {"type": "character_update", "payload": char.model_dump()})
    return char

class AdvanceAdd(BaseModel):
    # API now expects ID? Or should we keep name for convenience if unique?
    # User asked for "Identifiers separately".
    # Best is to use ID (int) from tree.
    # But for backward compat with my frontend changes, I might need to update frontend FIRST?
    # No, I should update backend to accept ID.
    node_id: int

# ... 

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
                    # key here refers to the identifier used by frontend. 
                    # If I update frontend to use ID, this should be an int.
                    # Or it could be the new 'key' string.
                    # Let's support ID if int, or name lookup if string (but name is ambiguous now).
                    # Actually, let's enforce ID or Key.
                    # Let's assume frontend sends { id: 123 }.
                    node_identifier = message.get("id")
                    
                    if node_identifier:
                        node_id = int(node_identifier)
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
                            # Maybe fetch name for response
                            response = f"Removed advance (ID: {node_id})"
                        else:
                            # Add
                            await pool.execute(
                                "INSERT INTO character_advances (character_id, advance_id) VALUES ($1, $2)", 
                                char_id, node_id
                            )
                            response = f"Added advance (ID: {node_id})"
                            
                            # Update points
                            cost = await pool.fetchval("SELECT cost FROM ability_nodes WHERE id = $1", node_id)
                            async with pool.acquire() as conn:
                                await conn.execute("UPDATE characters SET points_used = points_used + $1 WHERE id = $2", cost or 0, char_id)

                        updated = True
            
            elif message.get("type") == "command":
                text = message.get("text", "").lower()
                response = f"Command recognized: {text}"
                
                # Simple Health Parser
                # "Take X damage"
                damage_match = re.search(r'(take|suffer)\s+(\d+)', text)
                heal_match = re.search(r'(heal|recover)\s+(\d+)', text)
                set_match = re.search(r'set\s+health\s+(?:to\s+)?(\d+)', text)
                
                delta = 0
                set_val = None
                
                if damage_match:
                    delta = -int(damage_match.group(2))
                    response = f"Taking {-delta} damage."
                elif heal_match:
                    delta = int(heal_match.group(2))
                    response = f"Healing {delta} points."
                elif set_match:
                    set_val = int(set_match.group(1))
                    response = f"Health set to {set_val}."
                
                if delta != 0 or set_val is not None:
                     async with pool.acquire() as conn:
                        # Get current
                        curr = await conn.fetchval("SELECT health FROM characters WHERE id = $1", char_id)
                        max_hp = await conn.fetchval("SELECT max_health FROM characters WHERE id = $1", char_id) or 25
                        
                        if set_val is not None:
                            new_val = set_val
                        else:
                            new_val = curr + delta
                            
                        # Clamp?
                        new_val = max(0, min(new_val, max_hp))
                        
                        await conn.execute("UPDATE characters SET health = $1 WHERE id = $2", new_val, char_id)
                        updated = True

            if updated:
                async with pool.acquire() as conn:
                    updated_character = await get_character_internal(conn, char_id)
                await websocket.send_json({"response": response, "character": updated_character.model_dump()})
                await broadcast_tabletop(app, {"type": "character_update", "payload": updated_character.model_dump()})
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

        # Get node info via ID
        node = await conn.fetchrow("SELECT id, name, parent_id, cost FROM ability_nodes WHERE id = $1", advance.node_id)
        if not node:
             raise HTTPException(status_code=400, detail=f"Advance ID '{advance.node_id}' not found")
        
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
             parent_node = await conn.fetchrow("SELECT name, parent_id FROM ability_nodes WHERE id = $1", parent_id)
             # Only check parent if grandparent exists (i.e. parent is not a root category like "Playbooks" or "Basic Moves")
             if parent_node and parent_node['parent_id'] is not None: 
                  parent_owned = await conn.fetchval(
                      "SELECT 1 FROM character_advances WHERE character_id = $1 AND advance_id = $2",
                      char_id, parent_id
                  )
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
    
    # Fetch advances including ID
    adv_rows = await conn.fetch("""
        SELECT an.id, an.key, an.name, an.description, an.cost, ca.added_at 
        FROM character_advances ca
        JOIN ability_nodes an ON ca.advance_id = an.id
        WHERE ca.character_id = $1
    """, char_id)
    
    char_data['advances'] = [{
        "id": r['id'],
        "key": r['key'], 
        "name": r['name'],
        "description": r['description'],
        "cost": r['cost'], 
        "timestamp": int(r['added_at'].timestamp())
    } for r in adv_rows]
    
    # Mapping for frontend compatibility if models.py expects 'key' inside Dict?
    # models.py says List[Dict[str, Any]]. So keys are flexible.
    # But sheet.html accesses .key
    # I will inject 'key' = 'name' to keep it somewhat compatible or just handle it.

    # Fetch items
    item_rows = await conn.fetch("""
        SELECT ci.id, ci.item_id, ci.name as custom_name, ci.tags as custom_tags,
               i.name as base_name, i.description, i.tags as base_tags,
               i.type, i.stress
        FROM character_items ci
        JOIN items i ON ci.item_id = i.id
        WHERE ci.character_id = $1
    """, char_id)
    
    char_data['items'] = []
    for r in item_rows:
        name = r['custom_name'] if r['custom_name'] else r['base_name']
        tags = (r['base_tags'] or []) + (r['custom_tags'] or [])
        char_data['items'].append({
            "id": r['id'], 
            "item_id": r['item_id'],
            "name": name,
            "description": r['description'],
            "tags": tags,
            "type": r['type'],
            "stress": r['stress']
        })

    # Fetch links
    link_rows = await conn.fetch("""
        SELECT id, target_name, value
        FROM character_links
        WHERE character_id = $1
        ORDER BY id
    """, char_id)
    
    char_data['links'] = [dict(r) for r in link_rows]
    
    return Character(**char_data)

class MoveUpdate(BaseModel):
    description: str

@app.put("/api/moves/{move_id}")
async def update_move(move_id: int, move: MoveUpdate):
    pool = app.state.pool
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE ability_nodes SET description = $1 WHERE id = $2",
            move.description, move_id
        )
        if result == "UPDATE 0":
            raise HTTPException(status_code=404, detail="Move not found")
        return {"status": "ok", "id": move_id, "description": move.description}

@app.delete("/api/moves/{move_id}")
async def delete_move(move_id: int):
    pool = app.state.pool
    async with pool.acquire() as conn:
        # Cascade delete is handled by DB schema
        result = await conn.execute("DELETE FROM ability_nodes WHERE id = $1", move_id)
        if result == "DELETE 0":
             raise HTTPException(status_code=404, detail="Move not found")
    return {"status": "ok", "deleted": move_id}



@app.get("/api/items")
async def list_items():
    pool = app.state.pool
    rows = await pool.fetch("SELECT * FROM items ORDER BY type, name")
    return [dict(r) for r in rows]

@app.post("/characters/{char_id}/items", response_model=Character)
async def add_character_item(char_id: int, item_add: ItemAdd):
    pool = app.state.pool
    async with pool.acquire() as conn:
        char_exists = await conn.fetchval("SELECT 1 FROM characters WHERE id = $1", char_id)
        if not char_exists:
             raise HTTPException(status_code=404, detail="Character not found")
             
        item = await conn.fetchrow("SELECT name, tags FROM items WHERE id = $1", item_add.item_id)
        if not item:
             raise HTTPException(status_code=404, detail="Item not found")

        # Use provided name/tags or defaults (NULL in DB means fallback to item table in my query logic, 
        # but let's store NULL to imply 'inherit' or store snapshot?
        # My fetch logic uses coalesce.
        # If I want to allow renaming later, storing NULL is fine for "default".
        
        await conn.execute("""
            INSERT INTO character_items (character_id, item_id, name, tags)
            VALUES ($1, $2, $3, $4)
        """, char_id, item_add.item_id, item_add.name, item_add.tags)
        
        return await get_character_internal(conn, char_id)

@app.get("/characters/{char_id}/view-equipment", response_class=HTMLResponse)
async def view_equipment(request: Request, char_id: int):
    pool = app.state.pool
    char_exists = await pool.fetchval("SELECT 1 FROM characters WHERE id = $1", char_id)
    if not char_exists:
        raise HTTPException(status_code=404, detail="Character not found")
    return templates.TemplateResponse("equipment.html", {"request": request, "char_id": char_id})

@app.post("/characters/{char_id}/links", response_model=Character)
async def add_character_link(char_id: int, link: LinkAdd):
    pool = app.state.pool
    async with pool.acquire() as conn:
        char_exists = await conn.fetchval("SELECT 1 FROM characters WHERE id = $1", char_id)
        if not char_exists:
             raise HTTPException(status_code=404, detail="Character not found")
        
        await conn.execute("INSERT INTO character_links (character_id, target_name) VALUES ($1, $2)", char_id, link.target_name)
        
        return await get_character_internal(conn, char_id)

@app.websocket("/ws/tabletop")
async def websocket_tabletop(websocket: WebSocket):
    await websocket.accept()
    app.state.tabletop_connections.append(websocket)
    try:
        while True:
            # Just keep connection open, maybe handle pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        app.state.tabletop_connections.remove(websocket)
    except Exception as e:
        print(f"Tabletop WS Error: {e}")
        if websocket in app.state.tabletop_connections:
            app.state.tabletop_connections.remove(websocket)

@app.get("/tabletop", response_class=HTMLResponse)
async def view_tabletop(request: Request):
    return templates.TemplateResponse("tabletop.html", {"request": request})

@app.get("/select-map", response_class=HTMLResponse)
async def view_select_map(request: Request):
    return templates.TemplateResponse("select-map.html", {"request": request})

@app.get("/clocks", response_class=HTMLResponse)
async def view_clocks(request: Request):
    return templates.TemplateResponse("clocks.html", {"request": request})

@app.get("/api/maps")
async def list_maps():
    maps_dir = "static/maps"
    if not os.path.exists(maps_dir):
        return []
    files = [f for f in os.listdir(maps_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))]
    return files

@app.get("/api/clocks", response_model=List[Clock])
async def list_clocks():
    pool = app.state.pool
    rows = await pool.fetch("SELECT * FROM countdown_clocks ORDER BY id")
    return [dict(r) for r in rows]

@app.post("/api/clocks", response_model=Clock)
async def create_clock(clock: ClockCreate):
    pool = app.state.pool
    row = await pool.fetchrow(
        "INSERT INTO countdown_clocks (name, filled) VALUES ($1, $2) RETURNING *",
        clock.name, clock.filled
    )
    res = dict(row)
    await broadcast_tabletop(app, {"type": "clock_update", "payload": res})
    return res

@app.put("/api/clocks/{clock_id}", response_model=Clock)
async def update_clock(clock_id: int, clock: ClockUpdate):
    pool = app.state.pool
    async with pool.acquire() as conn:
        update_data = clock.model_dump(exclude_unset=True)
        if not update_data:
             row = await conn.fetchrow("SELECT * FROM countdown_clocks WHERE id = $1", clock_id)
        else:
             set_clauses = []
             values = []
             for i, (key, value) in enumerate(update_data.items(), start=1):
                 set_clauses.append(f"{key} = ${i}")
                 values.append(value)
             values.append(clock_id)
             row = await conn.fetchrow(
                 f"UPDATE countdown_clocks SET {', '.join(set_clauses)} WHERE id = ${len(values)} RETURNING *",
                 *values
             )
        
        if not row:
            raise HTTPException(status_code=404, detail="Clock not found")
        res = dict(row)
        await broadcast_tabletop(app, {"type": "clock_update", "payload": res})
        return res

@app.delete("/api/clocks/{clock_id}", status_code=204)
async def delete_clock(clock_id: int):
    pool = app.state.pool
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM countdown_clocks WHERE id = $1", clock_id)
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Clock not found")
    await broadcast_tabletop(app, {"type": "clock_delete", "payload": {"id": clock_id}})
    return None

@app.get("/api/gamestate", response_model=GameState)
async def get_gamestate():
    pool = app.state.pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT map_image FROM game_state ORDER BY id LIMIT 1")
        if not row:
            # Create default if not exists
            await conn.execute("INSERT INTO game_state (map_image) VALUES (NULL)")
            return {"map_image": None}
        return dict(row)

@app.put("/api/gamestate", response_model=GameState)
async def update_gamestate(state: GameStateUpdate):
    pool = app.state.pool
    async with pool.acquire() as conn:
        # Ensure row exists
        row = await conn.fetchrow("SELECT id FROM game_state ORDER BY id LIMIT 1")
        if not row:
             await conn.execute("INSERT INTO game_state (map_image) VALUES ($1)", state.map_image)
        else:
             await conn.execute("UPDATE game_state SET map_image = $1 WHERE id = $2", state.map_image, row['id'])
        
        res = {"map_image": state.map_image}
        await broadcast_tabletop(app, {"type": "gamestate_update", "payload": res})
        return res

if __name__ == "__main__":
    config = Config()
    config.bind = ["localhost:8000"]
    asyncio.run(serve(app, config))
