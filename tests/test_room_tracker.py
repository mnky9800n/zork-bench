"""Tests for RoomTracker and _detect_raw_room_name.

Room detection is the most fragile part of the harness — Zork reuses room
names (four Forest rooms, 15 maze rooms, etc.) and the tracker disambiguates
them via description substrings and prev-room/direction transitions. These
tests pin the three detection tiers:

  1. Unambiguous names (Living Room, Kitchen) — return as-is.
  2. Description-based (Forest "trees in all directions" -> Forest (1)).
  3. Transition-based (South of House + "south" -> Forest (3)).
"""

from zork_harness.agent import (
    RoomTracker,
    _detect_raw_room_name,
    _extract_direction,
    _looks_like_room_name,
)


# ---------------------------------------------------------------------------
# _looks_like_room_name
# ---------------------------------------------------------------------------

def test_looks_like_room_name_accepts_capitalized_short_line():
    assert _looks_like_room_name("Kitchen")
    assert _looks_like_room_name("West of House")
    assert _looks_like_room_name("Troll Room")


def test_looks_like_room_name_rejects_punctuation():
    assert not _looks_like_room_name("You are in a dark room.")
    assert not _looks_like_room_name("What do you want to do?")


def test_looks_like_room_name_rejects_prompts():
    assert not _looks_like_room_name(">take lamp")
    assert not _looks_like_room_name("[press any key]")


def test_looks_like_room_name_rejects_lowercase_start():
    assert not _looks_like_room_name("your score is 0")


def test_looks_like_room_name_rejects_too_long():
    assert not _looks_like_room_name("A" * 60)


# ---------------------------------------------------------------------------
# _detect_raw_room_name
# ---------------------------------------------------------------------------

def test_detect_raw_simple_case():
    output = "Kitchen\nYou are in the kitchen of the white house.\nA table seems to have been used."
    assert _detect_raw_room_name(output) == "Kitchen"


def test_detect_raw_skips_narrative_prefix():
    """Zork sometimes emits action-text before the room name."""
    output = "The trap door crashes shut, and you hear someone barring it.\n\nCellar\nYou are in a dark and damp cellar."
    assert _detect_raw_room_name(output) == "Cellar"


def test_detect_raw_returns_none_for_non_room_output():
    output = "Taken.\nYour score is 5 (total of 350 points), in 12 moves."
    assert _detect_raw_room_name(output) is None


def test_detect_raw_finds_room_after_death():
    """After 'you have died', the game respawns the player and prints a new room."""
    output = (
        "    ****  You have died  ****\n"
        "\n"
        "Now, let's take a look here... Well, you probably deserve another chance.\n"
        "\n"
        "Forest\n"
        "This is a forest, with trees in all directions."
    )
    assert _detect_raw_room_name(output) == "Forest"


# ---------------------------------------------------------------------------
# _extract_direction
# ---------------------------------------------------------------------------

def test_extract_direction_single_word():
    assert _extract_direction("north") == "north"
    assert _extract_direction("n") == "north"


def test_extract_direction_go_prefix():
    assert _extract_direction("go north") == "north"
    assert _extract_direction("go n") == "north"


def test_extract_direction_non_movement():
    assert _extract_direction("take lamp") is None
    assert _extract_direction("examine rug") is None


def test_extract_direction_empty_command():
    assert _extract_direction("") is None
    assert _extract_direction(None) is None


# ---------------------------------------------------------------------------
# RoomTracker: description-based disambiguation
# ---------------------------------------------------------------------------

def test_tracker_forest_1_detected_by_description():
    tracker = RoomTracker()
    output = "Forest\nThis is a forest, with trees in all directions."
    assert tracker.detect_room(output) == "Forest (1)"


def test_tracker_cave_near_hades_via_description():
    tracker = RoomTracker()
    output = "Cave\nThis is a damp cave leading down into darkness."
    assert tracker.detect_room(output) == "Cave (near Hades)"


def test_tracker_unambiguous_room_returns_raw_name():
    tracker = RoomTracker()
    output = "Living Room\nYou are in the living room. There is a doorway to the east."
    assert tracker.detect_room(output) == "Living Room"
    assert tracker.current_room == "Living Room"


# ---------------------------------------------------------------------------
# RoomTracker: transition-based disambiguation
# ---------------------------------------------------------------------------

def test_tracker_transition_south_of_house_south_forest_3():
    tracker = RoomTracker()
    tracker.detect_room("South of House\nYou are facing the south side of a white house.")
    assert tracker.current_room == "South of House"
    output = "Forest\nThis is a dimly lit forest, with large trees all around."
    assert tracker.detect_room(output, last_command="south") == "Forest (3)"


def test_tracker_transition_troll_room_west_maze_1():
    tracker = RoomTracker()
    tracker.detect_room("Troll Room\nThis is a small room with passages to the east and south.")
    output = "Maze\nThis is part of a maze of twisty little passages, all alike."
    assert tracker.detect_room(output, last_command="west") == "Maze (1)"


def test_tracker_maze_to_maze_transition():
    """Chained maze transitions must produce distinct rooms."""
    tracker = RoomTracker()
    tracker.detect_room("Troll Room\nThis is a small room.")
    tracker.detect_room("Maze\nTwisty passages.", last_command="west")
    assert tracker.current_room == "Maze (1)"
    # From Maze (1), go south -> Maze (2)
    result = tracker.detect_room("Maze\nTwisty passages.", last_command="south")
    assert result == "Maze (2)"


def test_tracker_transition_takes_precedence_over_description():
    """When both a transition entry and a description entry exist, transition wins."""
    tracker = RoomTracker()
    # Put tracker in South of House
    tracker.detect_room("South of House\nYou are facing the south side.")
    # Forest with 'trees in all directions' would match description -> Forest (1),
    # BUT the transition (South of House, south, Forest) resolves to Forest (3).
    output = "Forest\nThis is a forest, with trees in all directions."
    assert tracker.detect_room(output, last_command="south") == "Forest (3)"


def test_tracker_no_command_falls_through_to_description():
    """Without a last_command, transition lookup is skipped."""
    tracker = RoomTracker()
    tracker.detect_room("South of House\nYou are facing the south side.")
    output = "Forest\nThis is a forest, with trees in all directions."
    # No command -> description fires -> Forest (1)
    assert tracker.detect_room(output) == "Forest (1)"
