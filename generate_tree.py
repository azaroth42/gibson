import json
import re
import sys 

def to_kebab_case(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'\s+', '-', text)
    return text

def parse_advances(filepath):
    with open(filepath, 'r') as f:
        lines = f.readlines()

    tree = {}
    
    # Root structure
    tree["playbooks"] = {}
    
    # Parsing State
    current_root = None # The dict where we are adding items (e.g. mix-it-up, driver)
    
    stack = []          # Stack of node dicts for current advances tree
    indent_stack = []   # Stack of indentation levels
    
    context = "TOP"     # TOP, PLAYBOOKS, LIFE
    
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        if not stripped:
            i += 1
            continue

        # Header detection
        if stripped.lower().startswith('# playbooks'):
            context = "PLAYBOOKS"
            i += 1
            continue
        
        if stripped.lower().startswith('# health'):
            current_root = {"cost": 0, "children": []}
            tree["life"] = current_root
            stack = []
            indent_stack = []
            context = "LIFE"
            i += 1
            continue
            
        if stripped.startswith('## '):
            header = stripped.lstrip('# ').strip()
            
            # Check for "Move: Name"
            move_match = re.match(r'^Move:\s*(.*)', header, re.IGNORECASE)
            
            if move_match:
                name = move_match.group(1).strip()
                key = to_kebab_case(name)
                
                # If we are in PLAYBOOKS context, usually the moves are just descriptive details 
                # UNTIL we hit the "Advances" section for that Playbook.
                # However, looking at the file, Playbooks have their own sections.
                # ## Driver -> ### Move: Wheelman -> ### Advances
                
                # So if we are in TOP context, "Move: Mix It Up" defines a root.
                if context != "PLAYBOOKS":
                    current_root = {"cost": 0, "children": []}
                    tree[key] = current_root
                    stack = [] 
                    indent_stack = []
                
            elif header == "Health" or header == "Basic Statistics":
                 # Wait, "Health" is the section in new file.
                 # "## Health"
                 # It has "### Advances:"
                 # But in ability-tree.json target is "life".
                 pass

            # In "Health" section specifically
            if header == "Health":
                current_root = {"cost": 0, "children": []}
                tree["life"] = current_root
                stack = []
                indent_stack = []
            
            elif context == "PLAYBOOKS" and not move_match:
                # Likely a Playbook Name e.g. "Driver"
                # But headers might be "## Driver"
                name = header
                key = to_kebab_case(name)
                current_root = {"cost": 0, "children": []}
                tree["playbooks"][key] = current_root
                stack = []
                indent_stack = []
            
            i += 1
            continue

        # Subheaders "### Advances:" / "## Advances:" (Health uses ## Advances?)
        # Just check for "Advances" in header
        if "Advances" in stripped and stripped.startswith('#'):
            # This confirms we are ready to parse items for the current_root
            if current_root is not None:
                stack = [current_root]
                indent_stack = [-1] 
            i += 1
            continue

        # Parse Items: * [Cost] Text
        # Regex to capture indent, cost, and full text
        item_match = re.match(r'^(\s*)(?:[*+-]\s+)?\[(\d+)\]\s+(.*)', line)
        if item_match:
            if not stack:
                if current_root:
                     stack = [current_root]
                     indent_stack = [-1]
                else:
                    i += 1
                    continue
            
            indent_str = item_match.group(1)
            current_indent_len = 0
            for char in indent_str:
                if char == '\t':
                    current_indent_len += 4
                else:
                    current_indent_len += 1
            
            cost = int(item_match.group(2))
            raw_text = item_match.group(3).strip()
            
            # Key extraction logic
            # Check for explicit key "key: description" where key has no spaces
            key_match = re.match(r'^([^:\s]+):\s*(.*)', raw_text)
            if key_match:
                key_slug = key_match.group(1)
                desc = key_match.group(2)
            else:
                # No explicit key found (or key has spaces which means it's likely part of desc)
                desc = raw_text
                # Generate key from description
                # Take first few words? Or full slug?
                # User prefers concise keys, but we can't be too magical. 
                # Let's use full slug but maybe truncate if too long?
                # For now, standard slugify.
                key_slug = to_kebab_case(desc)
                # Ensure unique keys? (Not strictly handled here but tree dict overwrites checks?)
                # Actually tree is list of children, so duplicates allowed in list but keys in wrapper?
                # JSON structure: children: [ { "key": { ... } } ]
            
            # Multiline content handling
            j = i + 1
            while j < len(lines):
                next_line = lines[j]
                next_stripped = next_line.strip()
                if not next_stripped:
                    j += 1 
                    continue 
                
                if re.match(r'^\s*(?:[*+-]\s+)?\[\d+\]', next_line) or next_stripped.startswith('#'):
                     break
                
                desc += " " + next_stripped
                j += 1
                
            # Hierarchy Logic
            # "Strict" > check
            # Logic: valid child if indent > parent's indent.
            
            while len(indent_stack) > 1 and current_indent_len <= indent_stack[-1]:
                stack.pop()
                indent_stack.pop()
                
            parent = stack[-1]
            
            # Additional logic: 
            # If the current indent is exactly the same as parent indent, it is a SIBLING of the parent?
            # No, if same indent as previous item, it's a sibling.
            # wait, stack[-1] is the PARENT node.
            # indent_stack[-1] is the indent of that PARENT node.
            # So current_indent MUST be > indent_stack[-1] to be a child.
            
            if current_indent_len <= indent_stack[-1]:
                 # This shouldn't happen if we popped correctly?
                 # If we popped everything and still <= top level parent (indent -1), 
                 # then it's a top level item.
                 pass

            new_node = {
                "cost": cost,
                "description": desc,
                "children": []
            }
            
            wrapper = {key_slug: new_node}
            parent["children"].append(wrapper)
            
            stack.append(new_node)
            indent_stack.append(current_indent_len)
            
            i = j
            continue
            
        i += 1
        
    return tree

def write_tree(tree, output_file):
    with open(output_file, 'w') as f:
        json.dump(tree, f, indent=4)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python generate_tree.py <input_file> <output_file>")
        sys.exit(1)
        
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    tree = parse_advances(input_file)
    write_tree(tree, output_file)
