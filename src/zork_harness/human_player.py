"""Human play mode: drives a ZorkSession from keyboard input via the HumanMapViewer."""

import shlex

from zork_harness.agent import RoomTracker
from zork_harness.logger import SessionLogger
from zork_harness.session import ZorkSession
from zork_harness.tools import ToolRegistry

_HELP_TEXT = """\
/record <room> [dir=dest ...] [items=a,b,c]  — record a room and its exits/items
/lookup <room>                                — look up a recorded room
/rooms                                        — list all recorded rooms
/path <from> <to>                             — find a route between two rooms
/inv add <item>                               — add an item to inventory
/inv remove <item>                            — remove an item from inventory
/note <text>                                  — append a note to your scratchpad
/tool_help                                    — detailed tool descriptions and examples
/help                                         — show this help\
"""

_TOOL_HELP_TEXT = """\
=== Map Tools ===

/record <room> [dir=dest ...] [items=a,b,c]
  Record a room you've visited with its exits and items.
  Revisiting merges new info with existing data.
  Examples:
    /record Kitchen north="Living Room" south=Garden
    /record "West of House" north=Forest items=mailbox,mat
    /record Cellar up="Living Room" items=lamp,sword,nasty_knife

/lookup <room>
  Retrieve recorded exits and items for a room.
  Examples:
    /lookup Kitchen
    /lookup "West of House"

/rooms
  List every room you've recorded so far with their known exits.

/path <from> <to>
  Find a route between two recorded rooms (BFS over your map).
  Quote multi-word room names, or leave the destination unquoted.
  Examples:
    /path Kitchen "Living Room"
    /path Cellar West of House

=== Always Available ===

/inv <add|remove> <item>
  Track items you pick up or drop.
  Examples:
    /inv add brass lantern
    /inv remove leaflet

/note <text>
  Scratchpad for puzzle clues, observations, anything to remember.
  Examples:
    /note trapdoor in living room leads to cellar
    /note need to find a light source before going underground\
"""

_DIRECTIONS = {"north", "south", "east", "west", "northeast", "northwest",
               "southeast", "southwest", "up", "down", "in", "out",
               "n", "s", "e", "w", "ne", "nw", "se", "sw", "u", "d"}


def _parse_tool_command(raw: str) -> tuple[str, dict] | tuple[None, str]:
    """Parse a slash command into (tool_name, tool_input) or (None, error_message).

    Returns (None, message) for /help and parse errors — callers display the
    message directly without dispatching to the registry.
    """
    # Strip leading slash and tokenise, respecting quoted strings.
    try:
        tokens = shlex.split(raw[1:])
    except ValueError as exc:
        return None, f"Parse error: {exc}"

    if not tokens:
        return None, "Empty command. Type /help for available commands."

    verb = tokens[0].lower()
    args = tokens[1:]

    if verb == "help":
        return None, _HELP_TEXT

    if verb == "tool_help":
        return None, _TOOL_HELP_TEXT

    if verb == "record":
        return _parse_record(args)

    if verb == "lookup":
        return _parse_lookup(args)

    if verb == "rooms":
        return "list_known_rooms", {}

    if verb == "path":
        return _parse_path(args)

    if verb == "inv":
        return _parse_inv(args)

    if verb == "note":
        if not args:
            return None, "Usage: /note <text>"
        return "add_note", {"note": " ".join(args)}

    return None, f"Unknown command: /{verb}. Type /help for available commands."


def _parse_record(args: list[str]) -> tuple[str, dict] | tuple[None, str]:
    """/record <room_name> [dir=dest ...] [items=a,b,c]"""
    if not args:
        return None, "Usage: /record <room> [dir=dest ...] [items=a,b,c]"

    room_name = args[0]
    exits: dict[str, str] = {}
    items: list[str] = []

    for token in args[1:]:
        if "=" not in token:
            return None, f"Expected key=value, got: {token!r}"
        key, _, value = token.partition("=")
        key = key.lower()
        if key == "items":
            items = [i.strip() for i in value.split(",") if i.strip()]
        elif key in _DIRECTIONS:
            exits[key] = value
        else:
            return None, f"Unknown key: {key!r}. Use a direction or 'items'."

    return "record_room", {"room_name": room_name, "exits": exits, "items": items}


def _parse_lookup(args: list[str]) -> tuple[str, dict] | tuple[None, str]:
    """/lookup <room_name>"""
    if not args:
        return None, "Usage: /lookup <room>"
    return "look_up_room", {"room_name": " ".join(args)}


def _parse_path(args: list[str]) -> tuple[str, dict] | tuple[None, str]:
    """/path <from> <to> — each name may be a single quoted token or two bare words."""
    if len(args) < 2:
        return None, 'Usage: /path <from> <to>  (quote multi-word names: /path Kitchen "Living Room")'
    # shlex already handled quoted tokens, so args[0] and args[1] are the rooms.
    # If the user typed /path Kitchen Living Room without quotes, join excess tokens onto <to>.
    from_room = args[0]
    to_room = " ".join(args[1:])
    return "find_path", {"from_room": from_room, "to_room": to_room}


def _parse_inv(args: list[str]) -> tuple[str, dict] | tuple[None, str]:
    """/inv <add|remove> <item>"""
    if len(args) < 2:
        return None, "Usage: /inv <add|remove> <item>"
    action = args[0].lower()
    if action not in ("add", "remove"):
        return None, f"Expected 'add' or 'remove', got: {action!r}"
    item = " ".join(args[1:])
    return "update_inventory", {"action": action, "item": item}


def run_human_session(game: str, viewer, session_dir: str) -> None:
    """Run a human-controlled Zork session.

    Reads commands from viewer.get_command(), sends them to the game,
    displays output in the viewer, and logs everything to session_dir.

    Commands prefixed with '/' are intercepted and dispatched to the
    ToolRegistry rather than sent to the game.
    """
    logger = SessionLogger(session_dir, game=game, model="human", backend="human")
    session = ZorkSession(game)
    room_tracker = RoomTracker()
    registry = ToolRegistry(map_mode="explore")

    try:
        opening_text = session.start()
    except Exception as exc:
        viewer.log_event("command", command="[startup]", output=f"Failed to start game: {exc}")
        logger.finalize()
        viewer.close()
        return

    # Show opening text and detect starting room
    viewer.log_event("command", command="[game start]", output=opening_text)
    opening_room = room_tracker.detect_room(opening_text)
    if opening_room:
        viewer.set_room(opening_room)

    turn = 0

    try:
        while not viewer.closed.is_set():
            command = viewer.get_command(timeout=0.5)
            if command is None:
                continue

            turn += 1
            viewer.log_event("turn_start", turn=turn, room=viewer._current_room)

            if command.startswith("/"):
                _handle_tool_command(command, turn, registry, viewer, logger)
                continue

            try:
                game_output = session.send_command(command)
            except Exception as exc:
                game_output = f"[Error communicating with game: {exc}]"

            room = room_tracker.detect_room(game_output, last_command=command)
            if room:
                viewer.set_room(room)

            score = session.get_score()

            viewer.log_event("command", command=command, output=game_output, room=room)

            logger.log_turn(
                turn=turn,
                command=command,
                output=game_output,
                room=room,
                score=score,
            )
    finally:
        session.close()
        logger.finalize()


def _handle_tool_command(
    command: str,
    turn: int,
    registry: ToolRegistry,
    viewer,
    logger: SessionLogger,
) -> None:
    """Parse and execute a slash tool command, then log the result."""
    tool_name, payload = _parse_tool_command(command)

    if tool_name is None:
        # payload is an informational message (help text or parse error)
        viewer.log_event("command", command=command, output=payload)
        return

    result = registry.execute(tool_name, payload)

    viewer.log_event("tool_call", name=tool_name, input=payload, result=result)

    logger.log_turn(
        turn=turn,
        command=command,
        output="",
        room=None,
        tool_calls=[{"name": tool_name, "input": payload, "result": result}],
    )
