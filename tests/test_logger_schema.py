"""Tests for SessionLogger: round-trip a synthetic session and assert schema stability.

Downstream analysis (benchmark/analyze.py, benchmark/leaderboard.py) depends
on specific field names and shapes. This test pins the header/turn/summary
record schemas. When later roadmap items extend the schema (e.g. adding
`treasure_events` or `thinking_tokens`), update this test to include them
— *and* verify old session files remain parseable (analyze uses .get() with
default None, so additive changes are backwards-compatible).
"""

import json
import sys
from pathlib import Path

import pytest

from zork_harness.logger import SessionLogger

# Import analyze._parse_jsonl to confirm the logger output is round-trippable
# through the exact parser used by the benchmark pipeline.
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "benchmark"))
import analyze  # noqa: E402  (sys.path mutation above)


REQUIRED_HEADER_FIELDS = {
    "type", "game", "model", "backend", "map_mode", "player_type", "started_at",
}

REQUIRED_TURN_FIELDS = {
    "type", "turn", "command", "output", "tool_calls", "thinking", "reasoning",
    "room", "died", "score", "malformed", "input_tokens", "output_tokens",
    "thinking_chars", "timestamp",
}

REQUIRED_SUMMARY_FIELDS = {
    "type", "game", "model", "backend", "map_mode", "player_type",
    "total_turns", "deaths", "death_turns", "unique_rooms", "rooms_list",
    "rooms_recorded_by_model", "phantom_rooms", "phantom_room_count",
    "total_input_tokens", "total_output_tokens", "room_sequence", "timestamp",
}


def _read_jsonl(path: Path) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def test_header_written_on_init(tmp_session_dir):
    logger = SessionLogger(tmp_session_dir, game="zork1", model="test", backend="anthropic", map_mode="explore")
    logger.finalize()
    records = _read_jsonl(logger.jsonl_path)
    header = records[0]
    assert header["type"] == "header"
    assert REQUIRED_HEADER_FIELDS <= set(header.keys())
    assert header["player_type"] == "llm"


def test_human_backend_sets_player_type_human(tmp_session_dir):
    logger = SessionLogger(tmp_session_dir, game="zork1", model="", backend="human", map_mode="none")
    logger.finalize()
    records = _read_jsonl(logger.jsonl_path)
    assert records[0]["player_type"] == "human"


def test_turn_record_has_required_fields(tmp_session_dir):
    logger = SessionLogger(tmp_session_dir, game="zork1", model="test", backend="anthropic", map_mode="explore")
    logger.log_turn(
        turn=1,
        command="look",
        output="West of House\nYou are standing in an open field.",
        tool_calls=[{"name": "record_room", "input": {}, "result": "ok"}],
        thinking="Let me examine my surroundings.",
        reasoning=None,
        room="West of House",
        score=0,
        malformed=False,
        input_tokens=100,
        output_tokens=25,
    )
    logger.finalize()
    records = _read_jsonl(logger.jsonl_path)
    turns = [r for r in records if r["type"] == "turn"]
    assert len(turns) == 1
    assert REQUIRED_TURN_FIELDS <= set(turns[0].keys())
    assert turns[0]["command"] == "look"
    assert turns[0]["room"] == "West of House"


def test_turn_detects_death_from_output(tmp_session_dir):
    logger = SessionLogger(tmp_session_dir, game="zork1", model="test", backend="anthropic", map_mode="none")
    logger.log_turn(
        turn=5,
        command="attack troll",
        output="The troll's axe removes your head. You have died.",
        room="Troll Room",
    )
    logger.finalize()
    records = _read_jsonl(logger.jsonl_path)
    turn = next(r for r in records if r["type"] == "turn")
    assert turn["died"] is True
    summary = next(r for r in records if r["type"] == "summary")
    assert summary["deaths"] == 1
    assert summary["death_turns"] == [5]


def test_thinking_chars_counts_thinking_text_length(tmp_session_dir):
    """thinking_chars is the len() of the thinking arg; 0 when absent."""
    logger = SessionLogger(tmp_session_dir, game="zork1", model="test", backend="anthropic", map_mode="none")
    thinking_text = "I should examine my surroundings first."
    logger.log_turn(turn=1, command="look", output="", thinking=thinking_text)
    logger.log_turn(turn=2, command="look", output="", thinking=None)
    logger.finalize()
    records = _read_jsonl(logger.jsonl_path)
    turns = [r for r in records if r["type"] == "turn"]
    assert turns[0]["thinking_chars"] == len(thinking_text)
    assert turns[1]["thinking_chars"] == 0


def test_turn_parses_score_from_output_when_not_provided(tmp_session_dir):
    logger = SessionLogger(tmp_session_dir, game="zork1", model="test", backend="anthropic", map_mode="none")
    logger.log_turn(
        turn=10,
        command="score",
        output="Your score is 15 (total of 350 points), in 10 moves.",
        room=None,
    )
    logger.finalize()
    records = _read_jsonl(logger.jsonl_path)
    turn = next(r for r in records if r["type"] == "turn")
    assert turn["score"] == 15


def test_summary_aggregates_rooms_and_tokens(tmp_session_dir):
    logger = SessionLogger(tmp_session_dir, game="zork1", model="test", backend="anthropic", map_mode="explore")
    logger.log_turn(turn=1, command="", output="", room="West of House")
    logger.log_turn(turn=2, command="east", output="", room="Living Room")
    logger.log_turn(turn=3, command="west", output="", room="West of House")  # repeat
    logger.set_tokens(1500, 400)
    logger.finalize(recorded_rooms={"West of House", "Living Room", "PhantomRoom"})

    records = _read_jsonl(logger.jsonl_path)
    summary = next(r for r in records if r["type"] == "summary")
    assert REQUIRED_SUMMARY_FIELDS <= set(summary.keys())
    assert summary["total_turns"] == 3
    assert summary["unique_rooms"] == 2
    assert set(summary["rooms_list"]) == {"West of House", "Living Room"}
    assert summary["phantom_rooms"] == ["PhantomRoom"]
    assert summary["phantom_room_count"] == 1
    assert summary["total_input_tokens"] == 1500
    assert summary["total_output_tokens"] == 400
    assert len(summary["room_sequence"]) == 3


def test_output_parseable_by_analyze(tmp_session_dir):
    """The logger's JSONL must round-trip through analyze._parse_jsonl unchanged."""
    logger = SessionLogger(tmp_session_dir, game="zork1", model="test", backend="anthropic", map_mode="explore")
    logger.log_turn(turn=1, command="look", output="West of House\n", room="West of House", score=0,
                    input_tokens=100, output_tokens=25)
    logger.log_turn(turn=2, command="east", output="Living Room\n", room="Living Room", score=5,
                    input_tokens=120, output_tokens=30)
    logger.set_tokens(220, 55)
    logger.finalize()

    parsed = analyze._parse_jsonl(logger.jsonl_path)
    assert parsed["header"] is not None
    assert parsed["header"]["game"] == "zork1"
    assert len(parsed["turns"]) == 2
    assert parsed["summary"] is not None
    assert parsed["summary"]["total_turns"] == 2


def test_close_without_finalize_leaves_no_summary(tmp_session_dir):
    """Crash-path: close() must not emit a summary record."""
    logger = SessionLogger(tmp_session_dir, game="zork1", model="test", backend="anthropic", map_mode="none")
    logger.log_turn(turn=1, command="look", output="")
    logger.close()
    records = _read_jsonl(logger.jsonl_path)
    assert not any(r["type"] == "summary" for r in records)


def test_transcript_file_written(tmp_session_dir):
    logger = SessionLogger(tmp_session_dir, game="zork1", model="test", backend="anthropic", map_mode="none")
    logger.log_turn(turn=1, command="look", output="West of House", room="West of House")
    logger.finalize()
    with open(logger.txt_path, encoding="utf-8") as fh:
        content = fh.read()
    assert "Turn 1" in content
    assert "> look" in content
    assert "West of House" in content
