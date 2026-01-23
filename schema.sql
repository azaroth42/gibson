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
    advances JSONB DEFAULT '[]'::jsonb,
    items JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
