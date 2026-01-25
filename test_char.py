
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
        
        # Validate Only expected moves are present
        expected_basics = {
            "mix-it-up", "fight-another-day", "act-under-pressure", "first-aid", 
            "research", "assess", "fast-talk", "hit-the-streets", "assist", "stressed-out"
        }
        playbook_key = "killer"
        
        # We expect basics + playbook + nothing else
        # Note: keys in advances are what we received. 
        # Check against db keys.
        
        received_keys = set([k.lower() for k in keys])
        expected_keys = expected_basics | {playbook_key}
        
        missing = expected_keys - received_keys
        extra = received_keys - expected_keys
        
        assert not missing, f"Missing moves: {missing}"
        assert not extra, f"Extra moves found (should not be there): {extra}"
        
        print("Success: Correct moves found.")
        
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
