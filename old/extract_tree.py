
import json
import asyncio
import asyncpg
import os
from db import DATABASE_URL

async def extract():
    print("Connecting to DB...")
    conn = await asyncpg.connect(DATABASE_URL)
    
    print("Extracting hierarchy...")
    rows = await conn.fetch("SELECT id, key, description, cost, parent_id FROM ability_nodes ORDER BY id ASC")
    await conn.close()
    
    def make_node_struct(r):
        d = {}
        d['cost'] = r['cost']
        if r['description'] is not None:
            d['description'] = r['description']
        d['children'] = []
        return d

    id_map = {}
    roots = []
    
    for r in rows:
        id_map[r['id']] = {
            'key': r['key'],
            'data': make_node_struct(r),
            'parent_id': r['parent_id'],
        }

    for r in rows:
        node = id_map[r['id']]
        pid = node['parent_id']
        
        if pid is None:
            roots.append(node)
        else:
            parent = id_map[pid]
            wrapper = { node['key']: node['data'] }
            parent['data']['children'].append(wrapper)

    final_tree = {}
    
    for r in roots:
        # Special handling for playbooks category to match original JSON structure
        if r['key'] == 'playbooks':
            playbooks_dict = {}
            for wrapper in r['data']['children']:
                k = list(wrapper.keys())[0]
                v = wrapper[k]
                playbooks_dict[k] = v
            final_tree['playbooks'] = playbooks_dict
        else:
            final_tree[r['key']] = r['data']

    print(json.dumps(final_tree, indent=4))

if __name__ == '__main__':
    asyncio.run(extract())
