"""Shared pytest fixtures for the zork-harness test suite."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
RESULTS_DIR = REPO_ROOT / "benchmark" / "results"


@pytest.fixture
def sample_session_jsonl() -> Path:
    """A real recorded zork1 session log used as a source of game-output fixtures.

    Picking the most recent claude-sonnet-4-6 none-mode session gives us a
    transcript rich in maze/forest traversal, which is where the
    disambiguation edge cases we most want to exercise live.
    """
    path = RESULTS_DIR / "claude-sonnet-4-6" / "none" / "session_20260412T135923Z.jsonl"
    if not path.exists():
        pytest.skip(f"Fixture session missing: {path}")
    return path


@pytest.fixture
def sample_turns(sample_session_jsonl: Path) -> list[dict]:
    """Parsed turn records from the sample session."""
    turns: list[dict] = []
    with open(sample_session_jsonl, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("type") == "turn":
                turns.append(record)
    return turns


@pytest.fixture
def tmp_session_dir(tmp_path: Path) -> Path:
    """A throwaway directory for SessionLogger round-trip tests."""
    d = tmp_path / "session"
    d.mkdir()
    return d
