from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class CharacterCreate(BaseModel):
    name: str
    playbook: str

class Character(BaseModel):
    id: int
    name: str
    playbook: str
    tough: int = 0
    cool: int = 0
    sharp: int = 0
    style: int = 0
    chrome: int = 0
    health: int = 0
    max_health: int = 0
    experience: int = 0
    points_used: int = 0
    x: Optional[int] = None
    y: Optional[int] = None
    advances: List[Dict[str, Any]] = []
    items: List[Dict[str, Any]] = []
    links: List[Dict[str, Any]] = []
    contacts: List[Dict[str, Any]] = []

class CharacterUpdate(BaseModel):
    name: Optional[str] = None
    playbook: Optional[str] = None
    tough: Optional[int] = None
    cool: Optional[int] = None
    sharp: Optional[int] = None
    style: Optional[int] = None
    chrome: Optional[int] = None
    health: Optional[int] = None
    max_health: Optional[int] = None
    experience: Optional[int] = None
    points_used: Optional[int] = None
    x: Optional[int] = None
    y: Optional[int] = None
    # advances/items updates logic might be complex, generic for now
    advances: Optional[List[Dict[str, Any]]] = None
    items: Optional[List[Dict[str, Any]]] = None

class ItemAdd(BaseModel):
    item_id: int
    name: Optional[str] = None
    tags: Optional[List[str]] = None

class LinkAdd(BaseModel):
    target_name: str

class LinkUpdate(BaseModel):
    value: int

class Clock(BaseModel):
    id: int
    name: str
    filled: int
    x: Optional[int] = None
    y: Optional[int] = None

class ClockCreate(BaseModel):
    name: str
    filled: int = 0
    x: Optional[int] = None
    y: Optional[int] = None

class ClockUpdate(BaseModel):
    name: Optional[str] = None
    filled: Optional[int] = None
    x: Optional[int] = None
    y: Optional[int] = None

class GameState(BaseModel):
    map_image: Optional[str] = None

class GameStateUpdate(BaseModel):
    map_image: Optional[str] = None

class AdvanceAdd(BaseModel):
    node_id: int

class MoveUpdate(BaseModel):
    description: str

class ContactAdd(BaseModel):
    name: str
    description: Optional[str] = None
