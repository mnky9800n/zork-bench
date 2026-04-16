"""Zork I treasure tracking.

Two metrics, two puzzles:

  - **found**: the agent ran `take <treasure>` and the game replied with
    "Taken.". Walking past something does not count as finding it; the agent
    has to actually recognize the object as worth taking.
  - **deposited**: the agent ran `put/drop/place/insert <treasure> in trophy
    case` and the game replied with "Done.". This is its own puzzle because
    of Zork's carry limit: you generally cannot just hoard everything and
    walk it home, you have to plan trips.

This module hardcodes only the *noun synonyms* of the 20 canonical Zork I
treasures. Point values come from the score field at runtime; we do not
litigate which Zork edition's scoring table is correct.
"""

from __future__ import annotations

import re

# Synonym table. Each treasure has a stable id (used in metrics) and a list
# of synonyms ordered longest-first (so "platinum bar" matches before "bar").
ZORK1_TREASURES: list[dict] = [
    {"id": "egg",          "synonyms": ["jewel-encrusted egg", "jeweled egg", "golden egg", "egg"]},
    {"id": "painting",     "synonyms": ["painting", "portrait"]},
    {"id": "platinum_bar", "synonyms": ["platinum bar", "bar"]},
    {"id": "trunk",        "synonyms": ["trunk of jewels", "trunk"]},
    {"id": "pot_of_gold",  "synonyms": ["pot of gold", "pot"]},
    {"id": "skull",        "synonyms": ["crystal skull", "skull"]},
    {"id": "diamond",      "synonyms": ["huge diamond", "diamond"]},
    {"id": "bracelet",     "synonyms": ["sapphire bracelet", "bracelet"]},
    {"id": "bag_of_coins", "synonyms": ["bag of coins", "leather bag", "bag"]},
    {"id": "coffin",       "synonyms": ["gold coffin", "coffin"]},
    {"id": "scepter",      "synonyms": ["sceptre", "scepter"]},
    {"id": "coal",         "synonyms": ["small pile of coal", "coal"]},
    {"id": "torch",        "synonyms": ["ivory torch", "torch"]},
    {"id": "trident",      "synonyms": ["crystal trident", "trident"]},
    {"id": "egyptian_coin","synonyms": ["gold coin", "egyptian coin", "coin"]},
    {"id": "statue",       "synonyms": ["statue", "statuette"]},
    {"id": "chalice",      "synonyms": ["silver chalice", "chalice"]},
    {"id": "figurine",     "synonyms": ["jade figurine", "figurine"]},
    {"id": "jewels",       "synonyms": ["pile of jewels", "jewels"]},
    {"id": "rare_book",    "synonyms": ["rare book", "book"]},
]

# Flat (synonym, treasure_id) lookup, longest-synonym-first so multi-word
# synonyms like "platinum bar" win over single-word ones like "bar".
_SYNONYM_LOOKUP: list[tuple[str, str]] = sorted(
    [(syn.lower(), t["id"]) for t in ZORK1_TREASURES for syn in t["synonyms"]],
    key=lambda pair: -len(pair[0]),
)

_TAKE_VERBS = ("take", "get", "grab", "pick up")

_DEPOSIT_RE = re.compile(
    r"^(?:put|drop|place|insert)\s+(.+?)\s+in(?:to)?\s+(?:the\s+)?trophy\s+case\b",
    re.IGNORECASE,
)

_TAKEN_RE = re.compile(r"\bTaken\.")
_DONE_RE = re.compile(r"\bDone\.")


def _match_synonym(noun_phrase: str) -> str | None:
    """Return the treasure id for the longest synonym that appears as a whole
    token inside the noun phrase, else None.
    """
    lowered = noun_phrase.lower()
    for synonym, tid in _SYNONYM_LOOKUP:
        if re.search(rf"\b{re.escape(synonym)}\b", lowered):
            return tid
    return None


def _strip_take_verb(command: str) -> str | None:
    """If `command` starts with a take verb, return the rest (the noun phrase)."""
    lowered = command.lower().strip()
    for verb in _TAKE_VERBS:
        if lowered.startswith(verb + " "):
            return lowered[len(verb) + 1:].strip()
    return None


def match_take(command: str, output: str) -> str | None:
    """Return the treasure id if this turn is a successful treasure take, else None.

    Successful means: command starts with a take verb, the noun is a known
    treasure, and the game output contains "Taken." (so refused takes don't count).
    """
    if not command:
        return None
    noun = _strip_take_verb(command)
    if noun is None:
        return None
    tid = _match_synonym(noun)
    if tid is None:
        return None
    if not _TAKEN_RE.search(output):
        return None
    return tid


def match_deposit(command: str, output: str) -> str | None:
    """Return the treasure id if this turn is a successful trophy-case deposit, else None.

    Successful means: command matches a deposit pattern, the noun is a known
    treasure, and the game output contains "Done.".
    """
    if not command:
        return None
    m = _DEPOSIT_RE.match(command.strip())
    if not m:
        return None
    tid = _match_synonym(m.group(1))
    if tid is None:
        return None
    if not _DONE_RE.search(output):
        return None
    return tid


def find_treasure_events(turns: list[dict]) -> tuple[set[str], set[str]]:
    """Walk a list of per-turn records and return (found, deposited) sets.

    Used by analyze.py and leaderboard.py to derive treasure stats from any
    session log, including ones that predate treasure tracking in the logger.
    """
    found: set[str] = set()
    deposited: set[str] = set()
    for t in turns:
        cmd = t.get("command", "")
        out = t.get("output", "")
        tid = match_take(cmd, out)
        if tid:
            found.add(tid)
        tid = match_deposit(cmd, out)
        if tid:
            deposited.add(tid)
    return found, deposited


def all_treasure_ids() -> list[str]:
    """All known treasure ids in canonical order."""
    return [t["id"] for t in ZORK1_TREASURES]
