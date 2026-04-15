"""Tests for ToolRegistry: room merging, BFS pathfinding, inventory, dispatch.

These tests pin the tool contract. Any LLM session replay depends on this
behavior being identical turn-over-turn — e.g., repeated record_room calls
must merge (not overwrite) exits + items, which the LLM depends on when it
re-records a partially-seen room.
"""

import pytest
from zork_harness.tools import ToolRegistry, get_anthropic_schemas, get_openai_schemas


# ---------------------------------------------------------------------------
# record_room / merging
# ---------------------------------------------------------------------------

def test_record_room_creates_new_entry():
    reg = ToolRegistry(map_mode="explore")
    result = reg.record_room("Kitchen", {"west": "Living Room"}, ["bottle"])
    assert result["recorded"] == "Kitchen"
    assert reg.rooms["Kitchen"]["exits"] == {"west": "Living Room"}
    assert reg.rooms["Kitchen"]["items"] == ["bottle"]
    assert "Kitchen" in reg.recorded_rooms


def test_record_room_merges_exits_on_second_call():
    """Re-recording a room must merge exits, not replace them."""
    reg = ToolRegistry(map_mode="explore")
    reg.record_room("Kitchen", {"west": "Living Room"}, ["bottle"])
    reg.record_room("Kitchen", {"up": "Attic"}, [])
    assert reg.rooms["Kitchen"]["exits"] == {"west": "Living Room", "up": "Attic"}


def test_record_room_merges_items_without_duplicates():
    reg = ToolRegistry(map_mode="explore")
    reg.record_room("Kitchen", {}, ["bottle", "sack"])
    reg.record_room("Kitchen", {}, ["bottle", "lamp"])
    assert reg.rooms["Kitchen"]["items"] == ["bottle", "sack", "lamp"]


def test_record_room_new_exit_overrides_same_direction():
    """If a direction is recorded twice, the later call's value wins (dict.update behavior)."""
    reg = ToolRegistry(map_mode="explore")
    reg.record_room("A", {"north": "X"}, [])
    reg.record_room("A", {"north": "Y"}, [])
    assert reg.rooms["A"]["exits"]["north"] == "Y"


# ---------------------------------------------------------------------------
# look_up_room / list_known_rooms
# ---------------------------------------------------------------------------

def test_look_up_room_missing():
    reg = ToolRegistry(map_mode="explore")
    assert "not recorded" in reg.look_up_room("Nowhere")


def test_look_up_room_returns_stored_data():
    reg = ToolRegistry(map_mode="explore")
    reg.record_room("Kitchen", {"west": "Living Room"}, ["bottle"])
    result = reg.look_up_room("Kitchen")
    assert result == {"room": "Kitchen", "exits": {"west": "Living Room"}, "items": ["bottle"]}


def test_list_known_rooms_empty():
    reg = ToolRegistry(map_mode="explore")
    assert reg.list_known_rooms() == {"known_rooms": [], "count": 0}


def test_list_known_rooms_populated():
    reg = ToolRegistry(map_mode="explore")
    reg.record_room("A", {"north": "B"}, [])
    reg.record_room("B", {"south": "A"}, [])
    result = reg.list_known_rooms()
    assert result["count"] == 2
    assert set(result["known_rooms"].keys()) == {"A", "B"}


# ---------------------------------------------------------------------------
# find_path / BFS
# ---------------------------------------------------------------------------

def test_find_path_same_room():
    reg = ToolRegistry(map_mode="explore")
    reg.record_room("A", {}, [])
    assert reg.find_path("A", "A") == {"path": [], "steps": 0}


def test_find_path_one_hop():
    reg = ToolRegistry(map_mode="explore")
    reg.record_room("A", {"north": "B"}, [])
    reg.record_room("B", {"south": "A"}, [])
    result = reg.find_path("A", "B")
    assert result == {"path": [{"direction": "north", "room": "B"}], "steps": 1}


def test_find_path_multi_hop_picks_shortest():
    """BFS must return the shortest path, not the first one discovered."""
    reg = ToolRegistry(map_mode="explore")
    # Two routes A -> D: short (A -> D direct) vs long (A -> B -> C -> D)
    reg.record_room("A", {"north": "B", "east": "D"}, [])
    reg.record_room("B", {"east": "C"}, [])
    reg.record_room("C", {"south": "D"}, [])
    reg.record_room("D", {}, [])
    result = reg.find_path("A", "D")
    assert result["steps"] == 1
    assert result["path"] == [{"direction": "east", "room": "D"}]


def test_find_path_unreachable_returns_message():
    reg = ToolRegistry(map_mode="explore")
    reg.record_room("A", {}, [])
    reg.record_room("B", {}, [])
    assert "No known path" in reg.find_path("A", "B")


def test_find_path_source_unknown():
    reg = ToolRegistry(map_mode="explore")
    reg.record_room("B", {}, [])
    assert "Starting room not recorded" in reg.find_path("A", "B")


def test_find_path_destination_unknown():
    reg = ToolRegistry(map_mode="explore")
    reg.record_room("A", {}, [])
    assert "Destination room not recorded" in reg.find_path("A", "B")


def test_find_path_ignores_exit_to_unrecorded_room():
    """An exit pointing to a room we haven't recorded is a dead end for BFS."""
    reg = ToolRegistry(map_mode="explore")
    # A's north exit names a room we never record; the route must go via B.
    reg.record_room("A", {"north": "Ghost", "east": "B"}, [])
    reg.record_room("B", {"north": "C"}, [])
    reg.record_room("C", {}, [])
    result = reg.find_path("A", "C")
    assert result["steps"] == 2
    assert result["path"][0]["room"] == "B"


# ---------------------------------------------------------------------------
# Inventory + notes
# ---------------------------------------------------------------------------

def test_inventory_add_and_remove():
    reg = ToolRegistry(map_mode="explore")
    assert reg.update_inventory("add", "lamp") == ["lamp"]
    assert reg.update_inventory("add", "sword") == ["lamp", "sword"]
    assert reg.update_inventory("remove", "lamp") == ["sword"]


def test_inventory_add_dedupes():
    reg = ToolRegistry(map_mode="explore")
    reg.update_inventory("add", "lamp")
    reg.update_inventory("add", "lamp")
    assert reg.inventory == ["lamp"]


def test_inventory_remove_missing_is_noop():
    reg = ToolRegistry(map_mode="explore")
    reg.update_inventory("add", "lamp")
    assert reg.update_inventory("remove", "sword") == ["lamp"]


def test_add_note_accumulates():
    reg = ToolRegistry(map_mode="explore")
    assert "1" in reg.add_note("first")
    assert "2" in reg.add_note("second")
    assert reg.notes == ["first", "second"]


# ---------------------------------------------------------------------------
# Dispatch / execute()
# ---------------------------------------------------------------------------

def test_execute_dispatches_record_room():
    reg = ToolRegistry(map_mode="explore")
    out = reg.execute("record_room", {"room_name": "X", "exits": {}, "items": []})
    assert "X" in out
    assert "X" in reg.rooms


def test_execute_unknown_tool_returns_error():
    reg = ToolRegistry(map_mode="explore")
    out = reg.execute("nonexistent_tool", {})
    assert "Unknown tool" in out


# ---------------------------------------------------------------------------
# Schema generation — map_mode gating
# ---------------------------------------------------------------------------

def test_anthropic_schemas_omit_map_tools_when_none():
    schemas = get_anthropic_schemas(map_mode="none")
    names = {s["name"] for s in schemas}
    assert "record_room" not in names
    assert "update_inventory" in names


def test_anthropic_schemas_include_map_tools_in_explore():
    schemas = get_anthropic_schemas(map_mode="explore")
    names = {s["name"] for s in schemas}
    assert {"record_room", "look_up_room", "list_known_rooms", "find_path"} <= names


def test_openai_schemas_have_function_wrapper():
    schemas = get_openai_schemas(map_mode="explore")
    assert all(s["type"] == "function" for s in schemas)
    assert all("parameters" in s["function"] for s in schemas)


# ---------------------------------------------------------------------------
# Full-mode preload
# ---------------------------------------------------------------------------

def test_full_mode_preloads_zork1_map():
    reg = ToolRegistry(map_mode="full")
    # Just assert we loaded *something* canonical; don't couple to exact count.
    assert len(reg.rooms) > 0
    # West of House is Zork I's starting room and a known map_data entry.
    # Use a loose check so this test doesn't break if map_data is extended.
    assert any("House" in r for r in reg.rooms)
