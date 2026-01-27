
import json
import asyncio
import asyncpg
import os
from db import DATABASE_URL

# Use the env's python if running via shell, but here we are in script.
# Ensure asyncpg is available.

async def migrate():
    print("Starting migration...")
    conn = await asyncpg.connect(DATABASE_URL)
    
    # Load JSON
    with open('ability-tree.json', 'r') as f:
        data = json.load(f)

    # Clear existing data to avoid duplicates if re-run (though reset_db handles this)
    await conn.execute("TRUNCATE TABLE ability_nodes RESTART IDENTITY CASCADE")

    async def insert_node(key, description, cost, parent_id):
        # Insert and return ID
        row_id = await conn.fetchval('''
            INSERT INTO ability_nodes (key, description, cost, parent_id)
            VALUES ($1, $2, $3, $4)
            RETURNING id
        ''', key, description, cost, parent_id)
        return row_id

    async def process_children(children_list, parent_id):
        for child_wrapper in children_list:
            # { "key": { ... } }
            key = list(child_wrapper.keys())[0]
            val = child_wrapper[key]
            cost = val.get('cost', 0)
            desc = val.get('description', None)
            
            node_id = await insert_node(key, desc, cost, parent_id)
            
            if 'children' in val:
                await process_children(val['children'], node_id)

    # Process Root Keys
    for root_key, root_val in data.items():
        # Check if "playbooks" pattern (dict of nodes) or standard node
        # Standard node has "children" list.
        # "playbooks" has sub-keys which are nodes.
        
        is_standard_node = False
        if 'children' in root_val and isinstance(root_val['children'], list):
            is_standard_node = True
            
        if is_standard_node:
            cost = root_val.get('cost', 0)
            desc = root_val.get('description', None)
            root_id = await insert_node(root_key, desc, cost, None)
            await process_children(root_val['children'], root_id)
        else:
            # Category container (like playbooks)
            # We treat it as a node with no description, acts as folder
            root_id = await insert_node(root_key, None, 0, None)
            
            # Iterate sub-items
            for sub_key, sub_val in root_val.items():
                if isinstance(sub_val, dict):
                    cost = sub_val.get('cost', 0)
                    desc = sub_val.get('description', None)
                    sub_id = await insert_node(sub_key, desc, cost, root_id)
                    
                    if 'children' in sub_val:
                        await process_children(sub_val['children'], sub_id)

    print("Migration inserted data.")
    
    # --- Extraction ---
    print("\nExtracting hierarchy...")
    
    # Fetch all
    rows = await conn.fetch("SELECT id, key, description, cost, parent_id FROM ability_nodes ORDER BY id ASC")
    
    # Build map: id -> dict representing the node
    # We need to reconstruct the format.
    # Format: { "cost": x, "description": y, "children": [] }
    # But for "playbooks", the children are directly in the dict.
    
    # Helper to create proper node struct
    def make_node_struct(r):
        d = {}
        # Only add cost/desc if they exist or normalized?
        # JSON has explicit costs and descriptions.
        # If description is None, maybe omit specific fields?
        
        # In DB we stored 0 for cost if missing.
        d['cost'] = r['cost']
        if r['description'] is not None:
            d['description'] = r['description']
        
        # We will add children list here, convert later if needed
        d['children'] = []
        return d

    id_map = {}
    roots = []
    
    # First pass: create objects
    for r in rows:
        id_map[r['id']] = {
            'key': r['key'],
            'data': make_node_struct(r),
            'parent_id': r['parent_id'],
            'is_category_root': r['key'] == 'playbooks' # Special handling
        }

    # Second pass: link children
    for r in rows:
        node = id_map[r['id']]
        pid = node['parent_id']
        
        if pid is None:
            roots.append(node)
        else:
            parent = id_map[pid]
            # Add to parent's children
            # Parent children list contains wrappers: { key: data }
            # Wait, for "playbooks" (category root), children are just the node data keyed by name in the main dict.
            # But here `node['data']` is the object.
            # We will fix the structure of "playbooks" at the end.
            
            # Construct wrapper
            wrapper = { node['key']: node['data'] }
            parent['data']['children'].append(wrapper)

    # Reconstruct final tree dict
    final_tree = {}
    
    for r in roots:
        # r is like { key: 'playbooks', data: { cost:0, children:[wrapper, wrapper] } }
        if r['key'] == 'playbooks':
            # Convert children list [ {courier: {...}}, {driver: {...}} ]
            # Into dict { courier: {...}, driver: {...} }
            playbooks_dict = {}
            for wrapper in r['data']['children']:
                # wrapper is { key: val }
                k = list(wrapper.keys())[0]
                v = wrapper[k]
                playbooks_dict[k] = v
            final_tree['playbooks'] = playbooks_dict
        else:
            # Standard node
            final_tree[r['key']] = r['data']

    # Dump a snippet to verify
    print(json.dumps(final_tree, indent=2)[:500] + "\n...")
    
    # Optional: write to file to check full diff
    with open('extracted_tree.json', 'w') as f:
        json.dump(final_tree, f, indent=4)
        print("Written extracted_tree.json")

    await conn.close()

if __name__ == '__main__':
    asyncio.run(migrate())
