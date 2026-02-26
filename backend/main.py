import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from models import ChatRequest, ChatResponse, PlayerProfileRequest
from session import store
from tools import parse_csv_course_data
from agent import run_agent

app = FastAPI(title="AI Golf Caddy")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

@app.post("/session/new")
def new_session():
    session_id = store.create_session()
    return {"session_id": session_id}


# ---------------------------------------------------------------------------
# Course upload (WF-01)
# ---------------------------------------------------------------------------

@app.post("/upload-course")
async def upload_course(
    file: UploadFile = File(...),
    session_id: str = Form(...),
):
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found. Please refresh the page.")

    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported.")

    file_bytes = await file.read()

    try:
        holes, warnings = parse_csv_course_data(file_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    store.update_course_data(session_id, holes)

    course_name = holes[0].course_name if holes else "Unknown Course"
    message = f"Loaded {len(holes)} holes for {course_name}."
    if warnings:
        message += " Warnings: " + " | ".join(warnings)

    return {"message": message, "hole_count": len(holes), "course_name": course_name, "warnings": warnings}


# ---------------------------------------------------------------------------
# Chat (WF-02, WF-03)
# ---------------------------------------------------------------------------

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    session = store.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found. Please refresh the page.")

    try:
        reply, updated_history = run_agent(
            session_id=req.session_id,
            user_message=req.message,
            conversation_history=session.conversation_history,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    session.conversation_history = updated_history

    return ChatResponse(response=reply)


# ---------------------------------------------------------------------------
# Player profile (WF-04)
# ---------------------------------------------------------------------------

@app.post("/player-profile")
def save_profile(req: PlayerProfileRequest):
    session = store.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found. Please refresh the page.")

    store.update_player_profile(req.session_id, req.profile)
    return {"message": "Player profile saved.", "profile": req.profile.model_dump()}


# ---------------------------------------------------------------------------
# Serve frontend
# ---------------------------------------------------------------------------

frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")

app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

@app.get("/")
def serve_index():
    return FileResponse(os.path.join(frontend_dir, "index.html"))
