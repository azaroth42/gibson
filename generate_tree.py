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
    root_key = None     # The key name of current_root in tree
    
    stack = []          # Stack of node dicts for current advances tree
    indent_stack = []   # Stack of indentation levels
    
    context = "TOP"     # TOP, PLAYBOOKS, LIFE
    
    last_root_name = "" # Track for debug/logging
    
    
    # Re-impl loop
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        if not stripped:
            i += 1
            continue

        # Header detection
        if stripped.startswith('# '):
            header = stripped.lstrip('# ').strip().lower()
            if header == "playbooks":
                context = "PLAYBOOKS"
            elif header == "system:":
                context = "SYSTEM" # Or just continue parsing subheaders
            elif header == "basic moves":
                context = "MOVES"
            
            # Reset current root when switching major contexts? 
            # Not strict, handled by ## Headers
            i += 1
            continue
            
        if stripped.startswith('## '):
            header = stripped.lstrip('# ').strip()
            
            # Check for "Move: Name"
            move_match = re.match(r'^Move:\s*(.*)', header, re.IGNORECASE)
            
            if move_match:
                name = move_match.group(1).strip()
                key = to_kebab_case(name)
                
                # Determine where this move belongs
                if context == "PLAYBOOKS":
                    # Moves inside playbooks are typically moves *of* that playbook.
                    # But the request format for playbooks is:
                    # playbooks -> driver -> children -> (advances)
                    # "Move: Expert Wheelman" describes a starting move usually.
                    # Does it have advances? 
                    # If it has an "Advances:" section later, yes.
                    # BUT wait, the advances.md file structure:
                    # ## Driver
                    # ...
                    # ### Move: Expert Wheelman
                    # ...
                    # ### Advances:
                    # [2] ...
                    
                    # The advances usually hang off the Playbook Root, not the Move Root?
                    # Let's check `ability-tree.json` target format.
                    # drivers -> children -> (list of advances)
                    
                    # So "Move: Expert Wheelman" is just descriptive text unless it has its own tree?
                    # In `advances.md`:
                    # ## Driver
                    # ...
                    # ### Advances:
                    # [2] sweet-ride ...
                    
                    # So the advances belong to "Driver". 
                    # "Move: Expert Wheelman" doesn't seem to start a new tree root in JSON.
                    
                    pass 
                
                else: 
                    # Top level move (Mix It Up, etc)
                    current_root = {"cost": 0, "children": []}
                    tree[key] = current_root
                    stack = [] # Reset invalidates stack
                    indent_stack = []
                    last_root_name = key
                
            elif header == "Health and Statistics":
                current_root = {"cost": 0, "children": []}
                tree["life"] = current_root
                stack = []
                indent_stack = []
                last_root_name = "life"
            
            elif context == "PLAYBOOKS":
                # Likely a Playbook Name e.g. "Driver"
                name = header
                key = to_kebab_case(name)
                current_root = {"cost": 0, "children": []}
                tree["playbooks"][key] = current_root
                stack = []
                indent_stack = []
                last_root_name = f"playbooks/{key}"
            
            i += 1
            continue

        # Subheaders "### Advances:"
        if stripped.startswith('### Advances'):
            # This confirms we are ready to parse items for the current_root
            # Clear stack just in case, though headers did it.
            stack = [current_root]
            indent_stack = [-1] 
            i += 1
            continue

        # Parse Items: [Cost] key: Description
        # Regex: optional whitespace, [N], whitespace, key, colon, description
        # OR just [N] key: description?
        
        # Example: [1] damage1: Base damage is d6+1
        item_match = re.match(r'^(\s*)\[(\d+)\]\s+([^:]+):\s*(.*)', line)
        if item_match:
            if not stack:
                # Orphaned item or "Advances" header missing?
                # If we are in a section that implies root (like after ## Driver), 
                # maybe we can assume root is active?
                # But logical safety: if stack is empty, we can't add to parent.
                # However, if we just saw a header and created a root, we should have pushed it?
                # Ah, my logic above only pushed to stack on "### Advances". 
                # If "### Advances" is missing, we might fail.
                # Let's auto-push root if valid and stack empty.
                if current_root and not stack:
                     stack = [current_root]
                     indent_stack = [-1]
                elif not current_root:
                    print(f"Warning: Orphaned item (no root) at line {i+1}: {stripped}")
                    i += 1
                    continue
            
            indent_str = item_match.group(1)
            cost = int(item_match.group(2))
            key_slug = item_match.group(3).strip() # Explicit key!
            desc = item_match.group(4).strip()
            
            # Multiline description handling?
            # Check next lines
            j = i + 1
            while j < len(lines):
                next_line = lines[j]
                next_stripped = next_line.strip()
                if not next_stripped:
                    j += 1 # Include empty lines or break? usually break on next item
                    continue # loop to next line
                
                # Check if next line is a new item or header
                if re.match(r'^\s*\[\d+\]', next_line) or next_stripped.startswith('#'):
                     break
                
                # Append
                desc += " " + next_stripped
                j += 1
                
            # Hierarchy Logic
            current_indent_len = len(indent_str)
            
            # If indent > parent_indent -> Child of last added
            # If indent <= parent_indent -> Pop until parent is found (indent > parent's_indent ?)
            # Actually, standard logic:
            # stack[-1] is potential parent.
            # parent's indent was indent_stack[-1].
            # If current > parent_indent: valid child.
            # Else: pop stack.
            
            while len(indent_stack) > 1 and current_indent_len <= indent_stack[-1]:
                stack.pop()
                indent_stack.pop()
                
            parent = stack[-1]
            
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
