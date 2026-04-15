"""Tests for _extract_command (agent.py): regex that pulls '> command' from LLM text."""

from zork_harness.agent import _extract_command


def test_extracts_single_command():
    assert _extract_command("> go north") == "go north"


def test_extracts_last_when_multiple():
    """When the LLM emits multiple '>' lines, we use the last one."""
    text = "Let me think.\n> look\nActually no.\n> go north"
    assert _extract_command(text) == "go north"


def test_returns_none_when_no_command():
    assert _extract_command("I'm thinking about what to do next.") is None


def test_returns_none_on_empty_string():
    assert _extract_command("") is None


def test_strips_surrounding_whitespace():
    assert _extract_command(">   take lamp   ") == "take lamp"


def test_ignores_gt_in_middle_of_line():
    """'>' only counts at the start of a line (MULTILINE mode)."""
    assert _extract_command("I think x > y means go east") is None


def test_preserves_command_with_prepositions():
    assert _extract_command("> put egg in trophy case") == "put egg in trophy case"


def test_handles_prefix_reasoning():
    text = (
        "I've just arrived in the Kitchen. The bottle and brown sack look useful.\n"
        "> take all"
    )
    assert _extract_command(text) == "take all"


def test_multiline_reasoning_then_command():
    text = (
        "Turn plan:\n"
        "1. Examine the room.\n"
        "2. Pick up anything that isn't nailed down.\n"
        "\n"
        "> examine table"
    )
    assert _extract_command(text) == "examine table"


def test_no_space_after_gt():
    """'>command' with no space should still extract."""
    assert _extract_command(">inventory") == "inventory"
