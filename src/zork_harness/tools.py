"""Tool definitions and execution for the Zork LLM agent.

Provides three tools:
  look_up_map      - query room data from the static Zork 1 map
  update_inventory - maintain a running inventory list
  add_note         - append a free-form note for the agent's own use
"""

from zork_harness.map_data import ZORK1_MAP

# Anthropic tool schema format
TOOL_SCHEMAS: list[dict] = [
    {
        "name": "look_up_map",
        "description": (
            "Look up a room in the Zork 1 map. Returns the room's known exits, "
            "description, and any notable items. Useful for planning routes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "room_name": {
                    "type": "string",
                    "description": "The exact room name to look up (e.g. 'Living Room', 'Troll Room').",
                }
            },
            "required": ["room_name"],
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
    """Holds mutable agent state and dispatches tool calls."""

    def __init__(self) -> None:
        self.inventory: list[str] = []
        self.notes: list[str] = []

    def look_up_map(self, room_name: str) -> dict:
        room = ZORK1_MAP.get(room_name)
        if room is None:
            return {"error": f"Room '{room_name}' not in map. Known rooms: {sorted(ZORK1_MAP)}"}
        return room

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

    def execute(self, tool_name: str, tool_input: dict) -> str:
        """Dispatch a tool call and return the result as a string."""
        if tool_name == "look_up_map":
            result = self.look_up_map(**tool_input)
        elif tool_name == "update_inventory":
            result = self.update_inventory(**tool_input)
        elif tool_name == "add_note":
            result = self.add_note(**tool_input)
        else:
            result = {"error": f"Unknown tool: {tool_name}"}
        return str(result)
