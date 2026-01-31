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
    x INTEGER DEFAULT NULL,
    y INTEGER DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ability_nodes (
    id SERIAL PRIMARY KEY,
    key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    cost INTEGER DEFAULT 0,
    parent_id INTEGER REFERENCES ability_nodes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS items (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    tags TEXT[],
    type TEXT DEFAULT 'gear',
    stress BOOLEAN DEFAULT FALSE
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
    name TEXT,
    description TEXT,
    tags TEXT[],
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS character_links (
    id SERIAL PRIMARY KEY,
    character_id INTEGER REFERENCES characters(id) ON DELETE CASCADE,
    target_name TEXT,
    value INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS contacts (
    id SERIAL PRIMARY KEY,
    character_id INTEGER REFERENCES characters(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS countdown_clocks (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    filled INTEGER DEFAULT 0,
    x INTEGER DEFAULT NULL,
    y INTEGER DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS game_state (
    id SERIAL PRIMARY KEY,
    map_image TEXT
);

CREATE TABLE IF NOT EXISTS dw_characters (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    hero_class TEXT NOT NULL,
    level INTEGER DEFAULT 1,
    xp INTEGER DEFAULT 0,
    -- Stats
    str INTEGER DEFAULT 10,
    dex INTEGER DEFAULT 10,
    con INTEGER DEFAULT 10,
    "int" INTEGER DEFAULT 10,
    wis INTEGER DEFAULT 10,
    cha INTEGER DEFAULT 10,
    -- Vitals
    current_hp INTEGER DEFAULT 10,
    max_hp INTEGER DEFAULT 10,
    armor INTEGER DEFAULT 0,
    damage_die TEXT DEFAULT 'd6',
    -- RP
    alignment TEXT,
    look TEXT,
    race TEXT,
    coin INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dw_items (
    id SERIAL PRIMARY KEY,
    character_id INTEGER REFERENCES dw_characters(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    tags TEXT[],
    weight INTEGER DEFAULT 0,
    qty INTEGER DEFAULT 1
);

DROP TABLE IF EXISTS dw_reference_moves;
CREATE TABLE dw_reference_moves (
    id SERIAL PRIMARY KEY,
    class TEXT, -- NULL for Basic Moves
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    type TEXT DEFAULT 'basic' -- basic, starting, advanced
);
