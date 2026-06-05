"""Tests for the RemGlk JSON transport in session.py.

The unit tests exercise the pure parsing/framing helpers against the real shapes
RemGlk (bocfel) emits, captured from a live container:
  - update objects with a buffer window ("text") and grid window ("lines")
  - the player's echoed command as a run styled "input"
  - a trailing ">" prompt paragraph
  - window ids that change every turn (so detection must be structural, not by id)

The integration test (marked `integration`) drives an actual container and needs
Docker; run it with `pytest -m integration`.
"""

from __future__ import annotations

import json

import pytest

from zork_harness.session import (
    RemGlkSession,
    _decode_json_object,
    _extract_buffer_text,
    _extract_status_line,
    _select_input_request,
)


def char_reader(text: str):
    """Return a zero-arg callable yielding one character at a time, "" at EOF."""
    it = iter(text)
    return lambda: next(it, "")


# Real captured opening update (trimmed), bocfel + remglk, zork1.
OPENING_UPDATE = {
    "type": "update",
    "gen": 1,
    "windows": [
        {"id": 21, "type": "grid", "gridwidth": 80, "gridheight": 1},
        {"id": 18, "type": "buffer"},
    ],
    "content": [
        {
            "id": 21,
            "lines": [
                {"line": 0, "content": [
                    {"style": "alert",
                     "text": " West of House                          Score: 0  Moves: 0 "}
                ]},
            ],
        },
        {
            "id": 18,
            "clear": True,
            "text": [
                {"append": True, "content": [
                    {"style": "normal", "text": "ZORK I: The Great Underground Empire"}]},
                {"content": [{"style": "normal", "text": "West of House"}]},
                {"content": [{"style": "normal",
                              "text": "You are standing in an open field west of a white house."}]},
                {},
                {"content": [{"style": "normal", "text": ">"}]},
            ],
        },
    ],
    "input": [{"id": 28, "gen": 1, "type": "line", "maxlen": 99}],
}

# Real captured update after "open mailbox" — note the changed window ids and the
# echoed command styled "input".
AFTER_COMMAND_UPDATE = {
    "type": "update",
    "gen": 2,
    "content": [
        {
            "id": 31,
            "lines": [
                {"line": 0, "content": [
                    {"style": "alert",
                     "text": " West of House                          Score: 0  Moves: 1 "}
                ]},
            ],
        },
        {
            "id": 28,
            "text": [
                {"append": True, "content": [{"style": "input", "text": "open mailbox"}]},
                {"content": [{"style": "normal",
                              "text": "Opening the small mailbox reveals a leaflet."}]},
                {},
                {"content": [{"style": "normal", "text": ">"}]},
            ],
        },
    ],
    "input": [{"id": 28, "gen": 2, "type": "line", "maxlen": 99}],
}


# ---------------------------------------------------------------------------
# _decode_json_object  (framing)
# ---------------------------------------------------------------------------

def test_decode_single_object():
    obj = {"type": "update", "gen": 1}
    assert _decode_json_object(char_reader(json.dumps(obj))) == obj


def test_decode_object_with_leading_whitespace():
    obj = {"a": 1}
    assert _decode_json_object(char_reader("\n\n  " + json.dumps(obj))) == obj


def test_decode_stops_at_first_object_when_two_are_queued():
    """RemGlk emits one object then blocks; we must not consume the next one."""
    first = {"gen": 1}
    second = {"gen": 2}
    stream = json.dumps(first) + "\n" + json.dumps(second) + "\n"
    assert _decode_json_object(char_reader(stream)) == first


def test_decode_handles_braces_inside_strings():
    obj = {"text": "a } looks like { the end"}
    assert _decode_json_object(char_reader(json.dumps(obj))) == obj


def test_decode_nested_object_spanning_many_reads():
    assert _decode_json_object(char_reader(json.dumps(OPENING_UPDATE))) == OPENING_UPDATE


def test_decode_raises_eof_on_truncated_object():
    truncated = '{"type": "update", "gen":'
    with pytest.raises(EOFError):
        _decode_json_object(char_reader(truncated))


def test_decode_raises_eof_on_empty_stream():
    with pytest.raises(EOFError):
        _decode_json_object(char_reader(""))


# ---------------------------------------------------------------------------
# _extract_buffer_text
# ---------------------------------------------------------------------------

def test_buffer_text_extracts_prose_and_strips_prompt():
    text = _extract_buffer_text(OPENING_UPDATE)
    assert "ZORK I: The Great Underground Empire" in text
    assert "West of House" in text
    assert "open field" in text
    assert not text.rstrip().endswith(">")


def test_buffer_text_drops_echoed_command():
    """The 'input'-styled run is the player's command echoed back; it must not appear."""
    text = _extract_buffer_text(AFTER_COMMAND_UPDATE)
    assert "open mailbox" not in text
    assert "Opening the small mailbox reveals a leaflet." in text
    assert not text.rstrip().endswith(">")


def test_buffer_text_ignores_grid_windows():
    """A status-line-only update yields no prose."""
    grid_only = {"content": [OPENING_UPDATE["content"][0]]}
    assert _extract_buffer_text(grid_only) == ""


def test_buffer_text_preserves_internal_blank_lines():
    update = {"content": [{"id": 1, "text": [
        {"content": [{"style": "normal", "text": "line one"}]},
        {},
        {"content": [{"style": "normal", "text": "line two"}]},
    ]}]}
    assert _extract_buffer_text(update) == "line one\n\nline two"


def test_buffer_text_empty_update():
    assert _extract_buffer_text({}) == ""


# ---------------------------------------------------------------------------
# _extract_status_line
# ---------------------------------------------------------------------------

def test_status_line_extracted_from_grid():
    status = _extract_status_line(OPENING_UPDATE)
    assert "West of House" in status
    assert "Score: 0" in status
    assert "Moves: 0" in status


def test_status_line_ignores_buffer_windows():
    buffer_only = {"content": [OPENING_UPDATE["content"][1]]}
    assert _extract_status_line(buffer_only) == ""


def test_status_line_empty_update():
    assert _extract_status_line({}) == ""


# ---------------------------------------------------------------------------
# _select_input_request
# ---------------------------------------------------------------------------

def test_select_input_prefers_line_over_char():
    update = {"input": [
        {"id": 5, "gen": 3, "type": "char"},
        {"id": 9, "gen": 3, "type": "line"},
    ]}
    assert _select_input_request(update)["id"] == 9


def test_select_input_falls_back_to_char():
    update = {"input": [{"id": 5, "gen": 3, "type": "char"}]}
    assert _select_input_request(update)["type"] == "char"


def test_select_input_none_when_absent():
    assert _select_input_request({}) is None


# ---------------------------------------------------------------------------
# get_score  (no Docker: status line is cached directly)
# ---------------------------------------------------------------------------

def test_get_score_reads_cached_status_line():
    session = RemGlkSession("zork1")
    session._status_line = "West of House   Score: 25  Moves: 47"
    assert session.get_score() == 25


def test_get_score_none_before_any_status():
    session = RemGlkSession("zork1")
    assert session.get_score() is None


def test_unknown_game_rejected():
    with pytest.raises(ValueError):
        RemGlkSession("not-a-real-game")


# ---------------------------------------------------------------------------
# Integration: drive a real container  (needs Docker)
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_remglk_session_zork1_end_to_end():
    session = RemGlkSession("zork1")
    try:
        opening = session.start()
        assert "West of House" in opening
        assert session.get_score() == 0

        out = session.send_command("open mailbox")
        assert "mailbox" in out.lower()
        assert session.get_score() == 0  # opening the mailbox scores nothing

        out2 = session.send_command("north")
        assert out2.strip()  # produced some prose
    finally:
        session.close()
