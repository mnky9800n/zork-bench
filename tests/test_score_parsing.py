"""Tests for score-parsing regexes in SessionLogger and ZorkSession.

Both share the same two patterns:
  1. "your score is N"
  2. "score: N" / "score N"

These are exercised against the real shapes of dfrotz/Zork output.
"""

from zork_harness.logger import SessionLogger


def parse(output: str) -> int | None:
    return SessionLogger._parse_score(output)


def test_canonical_zork_score_line():
    """'Your score is N (total of M points).' — Zork's standard 'score' command reply."""
    assert parse("Your score is 25 (total of 350 points), in 47 moves.") == 25


def test_score_lowercase():
    assert parse("your score is 0") == 0


def test_score_embedded_in_longer_text():
    """Score lines sometimes appear after other game text (e.g. treasure deposits)."""
    text = (
        "Taken. A hollow voice says 'Fool.'\n"
        "Your score is 105 (total of 350 points), in 132 moves."
    )
    assert parse(text) == 105


def test_alternate_score_colon_format():
    """Some games use 'Score: N' instead."""
    assert parse("Score: 42") == 42


def test_no_score_returns_none():
    assert parse("You are in a dark room. It is pitch black.") is None


def test_empty_returns_none():
    assert parse("") is None


def test_first_match_wins_canonical_format():
    """If both formats are present, the canonical one takes precedence."""
    text = "Your score is 10. Score: 999."
    assert parse(text) == 10


def test_case_insensitive_score_matching():
    """The current implementation lowercases before matching."""
    assert parse("YOUR SCORE IS 7 (total of 350 points)") == 7


def test_score_zero_is_distinguishable_from_none():
    assert parse("Your score is 0 (total of 350 points), in 2 moves.") == 0
    assert parse("Your score is 0 (total of 350 points), in 2 moves.") is not None


def test_multi_digit_score():
    assert parse("Your score is 350 (total of 350 points), in 500 moves.") == 350
