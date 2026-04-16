"""Tests for treasure pickup / deposit detection.

Two metrics, two functions:
  - match_take(cmd, output) detects a successful `take <treasure>`.
  - match_deposit(cmd, output) detects a successful trophy-case deposit.
Both return the treasure id or None.
"""

from zork_harness.treasures import (
    ZORK1_TREASURES,
    all_treasure_ids,
    find_treasure_events,
    match_deposit,
    match_take,
)


# ---------------------------------------------------------------------------
# match_take
# ---------------------------------------------------------------------------

def test_take_egg_with_taken_confirmation():
    assert match_take("take egg", "Taken.\nYou hear chirping.") == "egg"


def test_take_with_get_synonym_verb():
    assert match_take("get painting", "Taken.") == "painting"


def test_take_with_pick_up_two_word_verb():
    assert match_take("pick up bracelet", "Taken.") == "bracelet"


def test_take_longer_synonym_wins():
    """'platinum bar' must take precedence over 'bar' alone."""
    assert match_take("take platinum bar", "Taken.") == "platinum_bar"


def test_take_without_taken_returns_none():
    """If the game refused the take, it does not count as found."""
    assert match_take("take egg", "I don't see any egg here.") is None


def test_take_of_non_treasure_returns_none():
    assert match_take("take lamp", "Taken.") is None


def test_take_word_boundary_prevents_partial_match():
    """'scarab' must not match the treasure synonym 'bar' (substring only)."""
    assert match_take("take scarab", "Taken.") is None


def test_take_empty_command_returns_none():
    assert match_take("", "Taken.") is None


def test_take_unrelated_verb_returns_none():
    assert match_take("examine egg", "It's a shiny jeweled egg.") is None


# ---------------------------------------------------------------------------
# match_deposit
# ---------------------------------------------------------------------------

def test_deposit_put_in_trophy_case():
    assert match_deposit("put painting in trophy case", "Done.") == "painting"


def test_deposit_drop_in_trophy_case():
    assert match_deposit("drop egg in trophy case", "Done.") == "egg"


def test_deposit_with_the_article():
    assert match_deposit("put trunk in the trophy case", "Done.") == "trunk"


def test_deposit_into_form():
    assert match_deposit("put coal into trophy case", "Done.") == "coal"


def test_deposit_without_done_returns_none():
    assert match_deposit("put egg in trophy case", "The trophy case is closed.") is None


def test_deposit_of_non_treasure_returns_none():
    assert match_deposit("put lamp in trophy case", "Done.") is None


def test_deposit_unrelated_command_returns_none():
    assert match_deposit("north", "You are in a forest.") is None


# ---------------------------------------------------------------------------
# find_treasure_events
# ---------------------------------------------------------------------------

def test_find_treasure_events_walks_turns():
    turns = [
        {"command": "take painting", "output": "Taken."},
        {"command": "take lamp", "output": "Taken."},  # not a treasure
        {"command": "put painting in trophy case", "output": "Done."},
    ]
    found, deposited = find_treasure_events(turns)
    assert found == {"painting"}
    assert deposited == {"painting"}


def test_find_treasure_events_dedupes():
    """A treasure taken twice should appear once in the found set."""
    turns = [
        {"command": "take egg", "output": "Taken."},
        {"command": "drop egg", "output": "Dropped."},
        {"command": "take egg", "output": "Taken."},
    ]
    found, deposited = find_treasure_events(turns)
    assert found == {"egg"}
    assert deposited == set()


def test_find_treasure_events_empty():
    assert find_treasure_events([]) == (set(), set())


def test_find_treasure_events_handles_missing_command_or_output():
    turns = [
        {"command": "", "output": ""},
        {},  # missing both keys
    ]
    assert find_treasure_events(turns) == (set(), set())


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------

def test_all_treasure_ids_returns_20_unique():
    ids = all_treasure_ids()
    assert len(ids) == 20
    assert len(set(ids)) == 20


def test_all_synonyms_lowercase_only():
    """Synonyms are matched lowercase; storing them lowercase avoids drift."""
    for t in ZORK1_TREASURES:
        for syn in t["synonyms"]:
            assert syn == syn.lower(), f"Synonym not lowercase: {syn!r}"
