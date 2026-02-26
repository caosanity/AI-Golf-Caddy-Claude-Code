import uuid
from models import SessionData, HoleRecord, PlayerProfile


class SessionStore:
    def __init__(self):
        self._store: dict[str, SessionData] = {}

    def create_session(self) -> str:
        session_id = str(uuid.uuid4())
        self._store[session_id] = SessionData(session_id=session_id)
        return session_id

    def get_session(self, session_id: str) -> SessionData | None:
        return self._store.get(session_id)

    def update_course_data(self, session_id: str, holes: list[HoleRecord]) -> None:
        session = self._store.get(session_id)
        if session:
            session.course_data = holes

    def update_player_profile(self, session_id: str, profile: PlayerProfile) -> None:
        session = self._store.get(session_id)
        if session:
            session.player_profile = profile

    def append_message(self, session_id: str, role: str, content) -> None:
        session = self._store.get(session_id)
        if session:
            session.conversation_history.append({"role": role, "content": content})


# Global singleton
store = SessionStore()
