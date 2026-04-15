"""Combined leaderboard for AI model runs and human playthroughs.

Walks benchmark/results/, computes max score and rooms visited for each
session, and prints two tables: AI models (grouped by model+mode) followed
by human playthroughs numbered by rank.

Human sessions live under benchmark/results/humans/ and are identified by
their header's player_type=="human" or backend=="human".

Usage:
    uv run python benchmark/leaderboard.py [--min-turns N]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load(path: Path) -> tuple[dict | None, list[dict]]:
    header = None
    turns = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("type") == "header":
                header = rec
            else:
                turns.append(rec)
    return header, turns


def _stats(turns: list[dict]) -> tuple[int, int, int, float | None]:
    """Return (n_turns, max_score, unique_rooms, mean_tokens_per_turn).

    mean_tokens_per_turn is None when no turn logged token usage (e.g. human
    sessions) — callers render this as '—'.
    """
    scores = [t.get("score") for t in turns if t.get("score") is not None]
    rooms = {t.get("room") for t in turns if t.get("room")}
    token_turns = [
        (t.get("input_tokens") or 0) + (t.get("output_tokens") or 0)
        for t in turns
        if t.get("input_tokens") is not None or t.get("output_tokens") is not None
    ]
    mean_tpt: float | None = sum(token_turns) / len(token_turns) if token_turns else None
    return len(turns), max(scores) if scores else 0, len(rooms), mean_tpt


def _is_human_session(header: dict | None) -> bool:
    if not header:
        return False
    return header.get("player_type") == "human" or header.get("backend") == "human"


def _best_per_leaf(results_dir: Path) -> list[Path]:
    """One JSONL per leaf directory: the session with the most turns.

    Using turn count (not mtime) avoids selecting stub sessions left behind
    by failed runs — the longest run is the most representative attempt.
    """
    by_parent: dict[Path, tuple[Path, int]] = {}
    for f in results_dir.rglob("session_*.jsonl"):
        _, turns = _load(f)
        n = len(turns)
        cur = by_parent.get(f.parent)
        if cur is None or n > cur[1]:
            by_parent[f.parent] = (f, n)
    return sorted(path for path, _ in by_parent.values())


def _fmt_tpt(tpt: float | None) -> str:
    if tpt is None:
        return "—"
    return f"{tpt:,.0f}"


def build_leaderboard(results_dir: Path, min_turns: int = 0):
    # Rows: (model, mode, turns, max_score, rooms, mean_tokens_per_turn)
    ai_rows: list[tuple] = []
    # Rows: (turns, max_score, rooms, mean_tokens_per_turn, session_name)
    human_rows: list[tuple] = []

    # AI runs: pick the longest session per <model>/<mode>/ directory
    for path in _best_per_leaf(results_dir):
        header, turns = _load(path)
        if _is_human_session(header):
            continue
        rel = path.relative_to(results_dir)
        parts = rel.parts
        if len(parts) < 3:
            continue  # not <model>/<mode>/session.jsonl
        model, mode = parts[0], parts[1]
        n_turns, max_score, rooms, mean_tpt = _stats(turns)
        if n_turns < min_turns:
            continue
        ai_rows.append((model, mode, n_turns, max_score, rooms, mean_tpt))

    # Human runs: every non-empty human session
    humans_dir = results_dir / "humans"
    if humans_dir.exists():
        for path in sorted(humans_dir.glob("session_*.jsonl")):
            header, turns = _load(path)
            if not _is_human_session(header) and header is not None:
                continue
            n_turns, max_score, rooms, mean_tpt = _stats(turns)
            if n_turns < min_turns:
                continue
            human_rows.append((n_turns, max_score, rooms, mean_tpt, path.stem))

    ai_rows.sort(key=lambda r: -r[3])
    human_rows.sort(key=lambda r: -r[1])

    header = f"{'Player':<22} {'Mode':<10} {'Turns':>6} {'MaxScore':>9} {'Rooms':>6} {'Tok/turn':>9}"
    sep = "-" * len(header)

    print(f"\n=== AI Models (min turns: {min_turns}) ===\n")
    print(header)
    print(sep)
    for model, mode, n_turns, max_score, rooms, mean_tpt in ai_rows:
        print(f"{model:<22} {mode:<10} {n_turns:>6} {max_score:>9} {rooms:>6} {_fmt_tpt(mean_tpt):>9}")

    print(f"\n=== Humans (min turns: {min_turns}) ===\n")
    human_header = f"{'Player':<22} {'Turns':>6} {'MaxScore':>9} {'Rooms':>6} {'Tok/turn':>9}  Session"
    print(human_header)
    print("-" * len(human_header))
    for i, (n_turns, max_score, rooms, mean_tpt, session_name) in enumerate(human_rows, start=1):
        print(f"{'human ' + str(i):<22} {n_turns:>6} {max_score:>9} {rooms:>6} {_fmt_tpt(mean_tpt):>9}  {session_name}")
    print()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path(__file__).parent / "results",
        help="Path to benchmark results directory.",
    )
    parser.add_argument(
        "--min-turns",
        type=int,
        default=100,
        help="Exclude sessions with fewer than this many turns (default: 100).",
    )
    args = parser.parse_args()
    build_leaderboard(args.results_dir, min_turns=args.min_turns)


if __name__ == "__main__":
    main()
