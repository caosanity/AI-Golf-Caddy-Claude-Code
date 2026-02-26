from pydantic import BaseModel
from typing import Optional


class Yardage(BaseModel):
    back: Optional[int] = None
    medium: Optional[int] = None
    front: Optional[int] = None


class HoleRecord(BaseModel):
    course_name: str
    hole_number: int
    par: int
    handicap: int
    yardage: Yardage
    special_notes: Optional[str] = ""


class PlayerProfile(BaseModel):
    handicap: Optional[float] = None
    club_distances: Optional[dict[str, int]] = None


class SessionData(BaseModel):
    session_id: str
    course_data: list[HoleRecord] = []
    player_profile: Optional[PlayerProfile] = None
    conversation_history: list[dict] = []


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    response: str


class PlayerProfileRequest(BaseModel):
    session_id: str
    profile: PlayerProfile
