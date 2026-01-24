CREATE TABLE IF NOT EXISTS characters (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    playbook TEXT NOT NULL,
    tough INTEGER DEFAULT 0,
    cool INTEGER DEFAULT 0,
    sharp INTEGER DEFAULT 0,
    style INTEGER DEFAULT 0,
    chrome INTEGER DEFAULT 0,
    health INTEGER DEFAULT 0,
    max_health INTEGER DEFAULT 0,
    experience INTEGER DEFAULT 0,
    points_used INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ability_nodes (
    id SERIAL PRIMARY KEY,
    key TEXT NOT NULL,
    description TEXT,
    cost INTEGER DEFAULT 0,
    parent_id INTEGER REFERENCES ability_nodes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS items (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    tags TEXT[],
    cost INTEGER DEFAULT 0,
    type TEXT DEFAULT 'gear'
);

CREATE TABLE IF NOT EXISTS character_advances (
    id SERIAL PRIMARY KEY,
    character_id INTEGER REFERENCES characters(id) ON DELETE CASCADE,
    advance_id INTEGER REFERENCES ability_nodes(id) ON DELETE CASCADE,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS character_items (
    id SERIAL PRIMARY KEY,
    character_id INTEGER REFERENCES characters(id) ON DELETE CASCADE,
    item_id INTEGER REFERENCES items(id) ON DELETE CASCADE,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
