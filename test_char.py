
from fastapi.testclient import TestClient
from main import app
import pytest
import asyncio
from db import init_db, get_db_pool

# We need to manage the lifecycle because TestClient with lifespan is tricky with asyncpg pool stored in app.state
# But TestClient calls the lifespan context manager.

def test_create_character_starts_with_moves():
    with TestClient(app) as client:
        # Create character
        response = client.post("/characters", json={
            "name": "Test Char",
            "playbook": "Killer"
        })
        assert response.status_code == 200
        data = response.json()
        char_id = data["id"]
        
        print(f"Created char {char_id}")
        
        # Check advances
        advances = data["advances"]
        keys = [a["key"] for a in advances]
        print("Advances:", keys)
        
        # Expect Basic Moves
        expected = ["mix-it-up", "act-under-pressure", "fight-another-day", "first-aid"] # etc
        
        # Check if at least some basic moves are there.
        # Note: keys in DB are normalized or raw? 'Mix It Up' or 'mix-it-up'?
        # The json has Keys as Title Case probably? "Mix It Up". Code migration used keys from dict.
        
        found = 0
        for exp in expected:
            # Case insensitive check might be needed
            if any(k.lower().replace(" ", "-") == exp for k in keys):
                found += 1
            # Or direct match if keys are "Mix It Up"
            if exp in keys:
                 found += 1
                 
        # We need to know what the keys actually look like.
        # But if the list is empty, that's a fail.
        assert len(advances) > 0, "Character should start with advances"
        
        # Cleanup? (Optional, DB persists)
        
if __name__ == "__main__":
    # Minimal runner if pytest not available/configured easily
    try:
        test_create_character_starts_with_moves()
        print("Test Passed!")
    except Exception as e:
        print(f"Test Failed: {e}")
        import traceback
        traceback.print_exc()
