"""Tool definitions and execution for the Zork LLM agent.

Provides six tools:
  record_room      - record a visited room (name, exits, items) into the agent's map
  look_up_room     - retrieve a previously recorded room from the agent's map
  list_known_rooms - list all rooms the agent has recorded so far
  find_path        - BFS path between two known rooms on the agent's self-built map
  update_inventory - maintain a running inventory list
  add_note         - append a free-form note for the agent's own use
"""

from collections import deque

# Anthropic tool schema format
TOOL_SCHEMAS: list[dict] = [
    {
        "name": "record_room",
        "description": (
            "Record a room you have just visited. Saves the room name, its visible exits, "
            "and any notable items. If the room was recorded before, the new exits and items "
            "are merged with the existing data so no information is lost."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "room_name": {
                    "type": "string",
                    "description": "The exact room name as printed by the game (e.g. 'Living Room').",
                },
                "exits": {
                    "type": "object",
                    "description": (
                        "A mapping of direction to destination room name. "
                        "Use only the directions you can see from this room "
                        "(e.g. {'north': 'Troll Room', 'south': 'Kitchen'}). "
                        "Use an empty object if no exits are visible."
                    ),
                    "additionalProperties": {"type": "string"},
                },
                "items": {
                    "type": "array",
                    "description": "Notable items or objects visible in this room.",
                    "items": {"type": "string"},
                },
            },
            "required": ["room_name", "exits", "items"],
        },
    },
    {
        "name": "look_up_room",
        "description": (
            "Look up a room you have previously recorded. "
            "Returns the room's exits and items, or a message if the room is not yet recorded."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "room_name": {
                    "type": "string",
                    "description": "The exact room name to look up (e.g. 'Living Room').",
                }
            },
            "required": ["room_name"],
        },
    },
    {
        "name": "list_known_rooms",
        "description": (
            "List every room you have recorded so far, along with its known exits. "
            "Useful for reviewing your map before planning a route."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "find_path",
        "description": (
            "Find a route between two rooms on your self-built map using the exits you have recorded. "
            "Returns the sequence of (direction, destination) steps to follow, "
            "or a message if no path is known."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "from_room": {
                    "type": "string",
                    "description": "The room to start from.",
                },
                "to_room": {
                    "type": "string",
                    "description": "The room to reach.",
                },
            },
            "required": ["from_room", "to_room"],
        },
    },
    {
        "name": "update_inventory",
        "description": (
            "Add or remove an item from your tracked inventory. "
            "Returns the full current inventory after the update."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "remove"],
                    "description": "Whether to add or remove the item.",
                },
                "item": {
                    "type": "string",
                    "description": "The item name.",
                },
            },
            "required": ["action", "item"],
        },
    },
    {
        "name": "add_note",
        "description": (
            "Append a note to your scratchpad. Useful for recording puzzle observations, "
            "room features, or anything you want to remember later."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "note": {
                    "type": "string",
                    "description": "The note text to record.",
                }
            },
            "required": ["note"],
        },
    },
]


class ToolRegistry:
    """Holds mutable agent state and dispatches tool calls.

    The agent's map is stored in self.rooms as:
        { room_name: {"exits": {direction: room_name, ...}, "items": [str, ...]} }

    Exits are treated as directed edges. A room only knows about exits the
    agent has explicitly recorded; unknown exits are absent from the dict.
    """

    def __init__(self, map_mode: str = "explore") -> None:
        self.map_mode = map_mode
        self.rooms: dict[str, dict] = {}
        self.inventory: list[str] = []
        self.notes: list[str] = []

        if map_mode == "full":
            self._preload_full_map()

    def _preload_full_map(self) -> None:
        """Load the complete static Zork 1 map into rooms."""
        from zork_harness.map_data import ZORK1_MAP
        for name, data in ZORK1_MAP.items():
            self.rooms[name] = {
                "exits": dict(data.get("exits", {})),
                "items": list(data.get("items", [])),
            }

    # ------------------------------------------------------------------
    # Map tools
    # ------------------------------------------------------------------

    def record_room(
        self,
        room_name: str,
        exits: dict[str, str],
        items: list[str],
    ) -> dict:
        """Upsert a room into the map, merging exits and items."""
        if room_name not in self.rooms:
            self.rooms[room_name] = {"exits": {}, "items": []}

        existing = self.rooms[room_name]

        # Merge exits: new values overwrite existing values for the same direction.
        existing["exits"].update(exits)

        # Merge items: append any items not already recorded.
        for item in items:
            if item not in existing["items"]:
                existing["items"].append(item)

        return {"recorded": room_name, "exits": existing["exits"], "items": existing["items"]}

    def look_up_room(self, room_name: str) -> dict | str:
        room = self.rooms.get(room_name)
        if room is None:
            return f"Room not recorded yet: '{room_name}'"
        return {"room": room_name, "exits": room["exits"], "items": room["items"]}

    def list_known_rooms(self) -> dict:
        if not self.rooms:
            return {"known_rooms": [], "count": 0}
        summary = {
            name: {"exits": list(data["exits"].keys()), "destinations": list(data["exits"].values())}
            for name, data in self.rooms.items()
        }
        return {"known_rooms": summary, "count": len(self.rooms)}

    def find_path(self, from_room: str, to_room: str) -> dict | str:
        """BFS over the recorded exit graph from from_room to to_room."""
        if from_room not in self.rooms:
            return f"Starting room not recorded yet: '{from_room}'"
        if to_room not in self.rooms:
            return f"Destination room not recorded yet: '{to_room}'"
        if from_room == to_room:
            return {"path": [], "steps": 0}

        # BFS: each queue entry is (current_room, path_so_far)
        # path_so_far is a list of (direction, destination) tuples
        queue: deque[tuple[str, list[tuple[str, str]]]] = deque()
        queue.append((from_room, []))
        visited: set[str] = {from_room}

        while queue:
            current, path = queue.popleft()
            room_data = self.rooms.get(current)
            if room_data is None:
                continue
            for direction, destination in room_data["exits"].items():
                if destination == to_room:
                    complete_path = path + [(direction, destination)]
                    return {
                        "path": [{"direction": d, "room": r} for d, r in complete_path],
                        "steps": len(complete_path),
                    }
                if destination not in visited and destination in self.rooms:
                    visited.add(destination)
                    queue.append((destination, path + [(direction, destination)]))

        return f"No known path from '{from_room}' to '{to_room}' using recorded exits."

    # ------------------------------------------------------------------
    # Inventory and notes
    # ------------------------------------------------------------------

    def update_inventory(self, action: str, item: str) -> list[str]:
        if action == "add":
            if item not in self.inventory:
                self.inventory.append(item)
        elif action == "remove":
            self.inventory = [i for i in self.inventory if i != item]
        return list(self.inventory)

    def add_note(self, note: str) -> str:
        self.notes.append(note)
        return f"Note recorded. Total notes: {len(self.notes)}"

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def execute(self, tool_name: str, tool_input: dict) -> str:
        """Dispatch a tool call and return the result as a string."""
        if tool_name == "record_room":
            result = self.record_room(**tool_input)
        elif tool_name == "look_up_room":
            result = self.look_up_room(**tool_input)
        elif tool_name == "list_known_rooms":
            result = self.list_known_rooms()
        elif tool_name == "find_path":
            result = self.find_path(**tool_input)
        elif tool_name == "update_inventory":
            result = self.update_inventory(**tool_input)
        elif tool_name == "add_note":
            result = self.add_note(**tool_input)
        else:
            result = {"error": f"Unknown tool: {tool_name}"}
        return str(result)

    def get_schemas(self) -> list[dict]:
        """Return tool schemas appropriate for the current map mode."""
        # Map tools that only make sense when the LLM can build/query a map
        map_tool_names = {"record_room", "look_up_room", "list_known_rooms", "find_path"}

        if self.map_mode == "none":
            # No map tools at all, just inventory and notes
            return [s for s in TOOL_SCHEMAS if s["name"] not in map_tool_names]
        else:
            # Both "explore" and "full" get all tools.
            # In "full" mode the map is pre-loaded but the LLM can still
            # record_room to update/correct it as it plays.
            return list(TOOL_SCHEMAS)
