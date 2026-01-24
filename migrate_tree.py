
import json
import asyncio
import asyncpg
import os
from db import DATABASE_URL

async def migrate():
    print("Starting migration...")
    conn = await asyncpg.connect(DATABASE_URL)
    
    # Load JSON
    with open('ability-tree.json', 'r') as f:
        data = json.load(f)

    # Clear existing data
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
            root_id = await insert_node(root_key, None, 0, None)
            
            for sub_key, sub_val in root_val.items():
                if isinstance(sub_val, dict):
                    cost = sub_val.get('cost', 0)
                    desc = sub_val.get('description', None)
                    sub_id = await insert_node(sub_key, desc, cost, root_id)
                    
                    if 'children' in sub_val:
                        await process_children(sub_val['children'], sub_id)

    print("Migration inserted data successfully.")
    await conn.close()

if __name__ == '__main__':
    asyncio.run(migrate())
