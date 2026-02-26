import os
import anthropic
from tools import dispatch_tool

SYSTEM_PROMPT = """You are an expert golf caddy. You have access to full course data for the round being played via your tools.

When asked about a hole, provide clear, actionable recommendations covering:
- Tee club & target line
- Layup or go-for-it decisions
- Hazards to avoid (specific, from course notes)
- Approach strategy and ideal yardage in
- Green: pin side, suggested landing zone
- A direct one-liner tip

Factor in player skill level (handicap, shot shape, club distances) and any real-time conditions the golfer provides (wind, lie, yardage).

Be direct and specific — no vague advice. Sound like a confident Tour caddy who knows the course cold.

If no course data has been loaded yet, tell the golfer to upload their course CSV first.
If no player profile exists, ask for their handicap, typical shot shape (draw/fade/straight), and key club distances before giving detailed recommendations.

Always use your tools to retrieve data — never invent hole details."""

TOOLS = [
    {
        "name": "get_hole_data",
        "description": "Retrieves a single hole's data record from session memory by hole number.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hole_number": {
                    "type": "integer",
                    "description": "The hole number to retrieve (1-18).",
                },
            },
            "required": ["hole_number"],
        },
    },
    {
        "name": "get_player_profile",
        "description": "Retrieves the current player's profile (handicap, shot shape, club distances) from session memory.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "calculate_adjusted_club",
        "description": "Recommends an adjusted club/yardage given wind, elevation, and lie conditions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "base_yardage": {
                    "type": "integer",
                    "description": "The straight-line yardage to the target.",
                },
                "wind_mph": {
                    "type": "number",
                    "description": "Wind speed in mph.",
                },
                "wind_direction": {
                    "type": "string",
                    "description": "Wind direction relative to shot: 'into', 'downwind', 'left', 'right', or 'none'.",
                },
                "elevation_change_ft": {
                    "type": "number",
                    "description": "Elevation change in feet (positive = uphill, negative = downhill).",
                },
                "lie": {
                    "type": "string",
                    "description": "Ball lie: 'fairway', 'rough', 'bunker', or 'tee'.",
                },
            },
            "required": ["base_yardage"],
        },
    },
    {
        "name": "generate_hole_recommendation",
        "description": "Assembles hole data, player profile, and situational context into a structured input for the caddy recommendation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hole_data": {
                    "type": "object",
                    "description": "The hole record from get_hole_data.",
                },
                "player_profile": {
                    "type": "object",
                    "description": "The player profile from get_player_profile (optional).",
                },
                "situational_context": {
                    "type": "string",
                    "description": "Any real-time conditions the golfer has mentioned (wind, lie, distance, pin position).",
                },
            },
            "required": ["hole_data"],
        },
    },
    {
        "name": "save_player_profile",
        "description": "Saves the player's profile (handicap, shot shape, club distances) to session memory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "profile": {
                    "type": "object",
                    "description": "Player profile object with fields: handicap (float), shot_shape (string), club_distances (object mapping club name to yardage int).",
                },
            },
            "required": ["profile"],
        },
    },
]


def run_agent(session_id: str, user_message: str, conversation_history: list[dict]) -> tuple[str, list[dict]]:
    """
    Run the Golf Caddy agent for one user turn.

    Args:
        session_id: The active session ID (used by tools to access session data).
        user_message: The latest message from the user.
        conversation_history: Prior messages in this session (mutated in place).

    Returns:
        (assistant_reply_text, updated_conversation_history)
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    # Append the new user message
    conversation_history.append({"role": "user", "content": user_message})

    # Agentic loop
    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=conversation_history,
        )

        # Append the raw assistant response (may contain tool_use blocks)
        conversation_history.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            # Extract the final text response
            text = next(
                (block.text for block in response.content if hasattr(block, "text")),
                "",
            )
            return text, conversation_history

        if response.stop_reason == "tool_use":
            # Execute each tool call and collect results
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result_json = dispatch_tool(block.name, block.input, session_id)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_json,
                    })

            # Feed results back to the model
            conversation_history.append({"role": "user", "content": tool_results})
            # Loop continues → model will process results and either call more tools or end_turn

        else:
            # Unexpected stop reason — surface the text if any and break
            text = next(
                (block.text for block in response.content if hasattr(block, "text")),
                f"[Stopped: {response.stop_reason}]",
            )
            return text, conversation_history
