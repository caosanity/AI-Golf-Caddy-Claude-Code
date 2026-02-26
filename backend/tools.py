import io
import json
import pandas as pd
from models import HoleRecord, PlayerProfile, Yardage
from session import store


# ---------------------------------------------------------------------------
# T-01: parse_csv_course_data
# ---------------------------------------------------------------------------

def parse_csv_course_data(file_bytes: bytes) -> tuple[list[HoleRecord], list[str]]:
    """Parse CSV bytes into a list of HoleRecord objects. Returns (holes, warnings)."""
    df = pd.read_csv(io.BytesIO(file_bytes))

    # Normalize column names: lowercase + strip whitespace for case-insensitive matching
    df.columns = [c.strip().lower() for c in df.columns]

    column_map = {
        "course name": "course_name",
        "hole number": "hole_number",
        "par": "par",
        "handicap for that hole": "handicap",
        "back tee yardage": "back",
        "medium tee yardage": "medium",
        "front tee yardage": "front",
        "special notes about that hole": "special_notes",
    }

    # Also accept common plural/alternate forms
    aliases = {
        "front tee yardages": "front tee yardage",
        "back tee yardages": "back tee yardage",
        "medium tee yardages": "medium tee yardage",
    }
    df.columns = [aliases.get(c, c) for c in df.columns]

    missing_cols = [col for col in column_map if col not in df.columns]
    if missing_cols:
        raise ValueError(f"CSV is missing required columns: {missing_cols}")

    holes: list[HoleRecord] = []
    warnings: list[str] = []

    for _, row in df.iterrows():
        hole_num = int(row["hole number"]) if pd.notna(row["hole number"]) else None
        if hole_num is None:
            warnings.append(f"Row with missing Hole Number skipped.")
            continue

        par = int(row["par"]) if pd.notna(row["par"]) else None
        if par not in (3, 4, 5):
            warnings.append(f"Hole {hole_num}: unusual par value '{par}'.")

        handicap = int(row["handicap for that hole"]) if pd.notna(row["handicap for that hole"]) else None

        def safe_int(val):
            try:
                return int(val) if pd.notna(val) else None
            except (ValueError, TypeError):
                return None

        yardage = Yardage(
            back=safe_int(row["back tee yardage"]),
            medium=safe_int(row["medium tee yardage"]),
            front=safe_int(row["front tee yardage"]),
        )

        holes.append(HoleRecord(
            course_name=str(row["course name"]),
            hole_number=hole_num,
            par=par,
            handicap=handicap,
            yardage=yardage,
            special_notes=str(row["special notes about that hole"]) if pd.notna(row["special notes about that hole"]) else "",
        ))

    if len(holes) != 18:
        warnings.append(f"Expected 18 holes, found {len(holes)}.")

    return holes, warnings


# ---------------------------------------------------------------------------
# T-02: get_hole_data
# ---------------------------------------------------------------------------

def get_hole_data(session_id: str, hole_number: int) -> dict:
    session = store.get_session(session_id)
    if not session or not session.course_data:
        return {"error": "No course data loaded for this session. Please upload a course CSV first."}

    for hole in session.course_data:
        if hole.hole_number == hole_number:
            return hole.model_dump()

    return {"error": f"Hole {hole_number} not found in the loaded course data."}


# ---------------------------------------------------------------------------
# T-03: get_player_profile
# ---------------------------------------------------------------------------

def get_player_profile(session_id: str) -> dict:
    session = store.get_session(session_id)
    if not session or not session.player_profile:
        return {"error": "No player profile set. Ask the golfer for their handicap, shot shape, and club distances."}
    return session.player_profile.model_dump()


# ---------------------------------------------------------------------------
# T-04: calculate_adjusted_club
# ---------------------------------------------------------------------------

def calculate_adjusted_club(
    base_yardage: int,
    wind_mph: float = 0,
    wind_direction: str = "none",
    elevation_change_ft: float = 0,
    lie: str = "fairway",
) -> dict:
    adjusted = float(base_yardage)

    # Wind adjustment: ~1 yard per 1 mph into wind, ~0.7 yard downwind
    if wind_direction in ("into", "headwind", "against"):
        adjusted += wind_mph * 1.0
    elif wind_direction in ("downwind", "helping", "with"):
        adjusted -= wind_mph * 0.7

    # Elevation: roughly 1 yard per 1 ft of elevation gain uphill
    adjusted += elevation_change_ft * 1.0

    # Lie penalty: rough adds ~10%, bunker adds ~15%
    if lie == "rough":
        adjusted *= 1.10
    elif lie == "bunker":
        adjusted *= 1.15

    adjusted = round(adjusted)

    # Simple club suggestion based on adjusted yardage
    clubs = [
        (300, "Driver"), (275, "3-wood"), (255, "5-wood"),
        (235, "3-hybrid"), (220, "4-hybrid"), (205, "4-iron"),
        (190, "5-iron"), (175, "6-iron"), (160, "7-iron"),
        (145, "8-iron"), (130, "9-iron"), (115, "Pitching Wedge"),
        (95, "Gap Wedge"), (75, "Sand Wedge"), (0, "Lob Wedge"),
    ]
    club = "Lob Wedge"
    for yardage_threshold, club_name in clubs:
        if adjusted >= yardage_threshold:
            club = club_name
            break

    return {
        "base_yardage": base_yardage,
        "adjusted_yardage": adjusted,
        "club_suggestion": club,
        "factors_applied": {
            "wind_mph": wind_mph,
            "wind_direction": wind_direction,
            "elevation_change_ft": elevation_change_ft,
            "lie": lie,
        },
    }


# ---------------------------------------------------------------------------
# T-05: generate_hole_recommendation
# ---------------------------------------------------------------------------

def generate_hole_recommendation(
    hole_data: dict,
    player_profile: dict | None = None,
    situational_context: str = "",
) -> dict:
    """
    Returns a structured dict the agent can use to compose its caddy response.
    The agent's LLM reasoning handles the actual prose generation.
    This tool assembles the key facts so the agent doesn't have to re-fetch them.
    """
    return {
        "hole_data": hole_data,
        "player_profile": player_profile,
        "situational_context": situational_context,
        "instruction": (
            "Using the hole_data, player_profile, and situational_context provided, "
            "generate a complete caddy recommendation covering: "
            "(1) Tee shot — club, target line, shape; "
            "(2) Layup/approach strategy — ideal yardage to leave; "
            "(3) Hazards to avoid — specific call-outs from special_notes; "
            "(4) Green — pin side, suggested landing zone; "
            "(5) One-liner tip."
        ),
    }


# ---------------------------------------------------------------------------
# T-06: save_player_profile
# ---------------------------------------------------------------------------

def save_player_profile(session_id: str, profile_data: dict) -> dict:
    profile = PlayerProfile(
        handicap=profile_data.get("handicap"),
        shot_shape=profile_data.get("shot_shape"),
        club_distances=profile_data.get("club_distances"),
    )
    store.update_player_profile(session_id, profile)
    return {"status": "saved", "profile": profile.model_dump()}


# ---------------------------------------------------------------------------
# Tool registry — maps tool names to callables for the agent loop
# ---------------------------------------------------------------------------

TOOL_REGISTRY = {
    "get_hole_data": lambda args, sid: get_hole_data(sid, args["hole_number"]),
    "get_player_profile": lambda args, sid: get_player_profile(sid),
    "calculate_adjusted_club": lambda args, sid: calculate_adjusted_club(**args),
    "generate_hole_recommendation": lambda args, sid: generate_hole_recommendation(
        args.get("hole_data", {}),
        args.get("player_profile"),
        args.get("situational_context", ""),
    ),
    "save_player_profile": lambda args, sid: save_player_profile(sid, args.get("profile", {})),
}


def dispatch_tool(tool_name: str, tool_input: dict, session_id: str) -> str:
    if tool_name not in TOOL_REGISTRY:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    result = TOOL_REGISTRY[tool_name](tool_input, session_id)
    return json.dumps(result)
