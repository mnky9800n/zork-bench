"""Benchmark analysis script for zork-harness JSONL session logs.

Reads session JSONL files from benchmark/results/, computes per-session metrics,
and produces a console table, a CSV, and (optionally) matplotlib charts.

Usage:
    python benchmark/analyze.py [--results-dir PATH]
"""

import argparse
import csv
import json
import math
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _parse_jsonl(path: Path) -> dict[str, Any]:
    """Parse a single JSONL session file into header, turns, and summary dicts."""
    header = None
    turns = []
    summary = None

    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            rtype = record.get("type")
            if rtype == "header":
                header = record
            elif rtype == "turn":
                turns.append(record)
            elif rtype == "summary":
                summary = record

    return {"header": header, "turns": turns, "summary": summary, "path": path}


def _most_recent_jsonl(directory: Path) -> Path | None:
    """Return the most recently modified .jsonl file in a directory, or None."""
    candidates = list(directory.glob("session_*.jsonl"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _is_human_session(parsed: dict[str, Any]) -> bool:
    """Treat a session as human if its header says so. Falls back to backend."""
    header = parsed.get("header") or {}
    return header.get("player_type") == "human" or header.get("backend") == "human"


def load_all_sessions(results_dir: Path) -> list[dict[str, Any]]:
    """Walk results_dir and return parsed sessions.

    AI sessions: layout is results/<model>/<map_mode>/session_*.jsonl. We pick
    the most recent session per leaf directory so each (model, map_mode) cell
    in the matrix has exactly one row.

    Human sessions: layout is results/humans/session_*.jsonl. We load every
    session so each playthrough appears as its own row in the humans table
    (same behavior as leaderboard.py).
    """
    sessions = []

    # Collect all directories that contain at least one session_*.jsonl file.
    seen_dirs: set[Path] = set()
    for jsonl_path in sorted(results_dir.rglob("session_*.jsonl")):
        seen_dirs.add(jsonl_path.parent)

    for directory in sorted(seen_dirs):
        rel = directory.relative_to(results_dir)
        parts = rel.parts
        is_humans_dir = parts == ("humans",)

        if is_humans_dir:
            # Every human playthrough is its own row.
            paths = sorted(directory.glob("session_*.jsonl"))
        else:
            recent = _most_recent_jsonl(directory)
            paths = [recent] if recent is not None else []

        for jsonl_path in paths:
            # Derive model and map_mode from the path. AI dirs use
            # <model>/<mode>; the humans dir has no map_mode subdir, so we
            # mark the row 'humans' / 'human' for the table grouping.
            if is_humans_dir:
                model_nickname = jsonl_path.stem  # session_<timestamp>
                map_mode = "human"
            elif len(parts) >= 2:
                model_nickname, map_mode = parts[0], parts[1]
            elif len(parts) == 1:
                model_nickname, map_mode = parts[0], "unknown"
            else:
                model_nickname, map_mode = "unknown", "unknown"

            parsed = _parse_jsonl(jsonl_path)
            parsed["model_nickname"] = model_nickname
            parsed["map_mode_dir"] = map_mode
            sessions.append(parsed)

    return sessions


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------

def _forward_fill_scores(turns: list[dict]) -> list[int | None]:
    """Return a list of scores, forward-filling None values from the last known score."""
    filled = []
    last = None
    for t in turns:
        s = t.get("score")
        if s is not None:
            last = s
        filled.append(last)
    return filled


def compute_metrics(session: dict[str, Any]) -> dict[str, Any]:
    """Derive all benchmark metrics from a parsed session dict."""
    header = session.get("header") or {}
    turns = session.get("turns") or []
    summary = session.get("summary") or {}
    model_nickname = session.get("model_nickname", "unknown")
    map_mode = session.get("map_mode_dir", "unknown")

    # --- Scores ---
    filled_scores = _forward_fill_scores(turns)
    final_score = filled_scores[-1] if filled_scores else None
    max_score = max((s for s in filled_scores if s is not None), default=None)

    # Score progression: (turn_number, score) only at change points
    score_progression: list[tuple[int, int]] = []
    prev = None
    for turn_record, score in zip(turns, filled_scores):
        if score is not None and score != prev:
            score_progression.append((turn_record["turn"], score))
            prev = score

    # --- Room tracking ---
    if summary.get("unique_rooms") is not None:
        unique_rooms = summary["unique_rooms"]
    else:
        unique_rooms = len({t["room"] for t in turns if t.get("room")})

    # Room discovery curve: cumulative unique rooms at each turn
    room_discovery_curve: list[tuple[int, int]] = []
    seen_rooms: set[str] = set()
    for t in turns:
        r = t.get("room")
        if r:
            seen_rooms.add(r)
        room_discovery_curve.append((t["turn"], len(seen_rooms)))

    # --- Malformed turns ---
    malformed_turns = sum(1 for t in turns if t.get("malformed"))
    malformed_tokens = sum(
        (t.get("input_tokens") or 0) + (t.get("output_tokens") or 0)
        for t in turns if t.get("malformed")
    )

    # --- Deaths ---
    if summary.get("deaths") is not None:
        total_deaths = summary["deaths"]
    else:
        total_deaths = sum(1 for t in turns if t.get("died"))

    death_turns: list[int] = summary.get("death_turns") or [
        t["turn"] for t in turns if t.get("died")
    ]

    total_turns = summary.get("total_turns") or (turns[-1]["turn"] if turns else 0)

    death_rate = total_deaths / total_turns if total_turns > 0 else float("inf")

    if len(death_turns) >= 2:
        diffs = [death_turns[i + 1] - death_turns[i] for i in range(len(death_turns) - 1)]
        mean_turns_between_deaths: float | None = sum(diffs) / len(diffs)
    else:
        mean_turns_between_deaths = None

    # --- Tokens ---
    total_input_tokens = summary.get("total_input_tokens", 0) or 0
    total_output_tokens = summary.get("total_output_tokens", 0) or 0
    total_tokens = total_input_tokens + total_output_tokens

    tokens_per_room = total_tokens / unique_rooms if unique_rooms > 0 else float("inf")

    if final_score and final_score > 0:
        tokens_per_score_point = total_tokens / final_score
    else:
        tokens_per_score_point = float("inf")

    # --- Per-turn token distribution (roadmap item #5) ---
    # Series of total tokens spent on each turn. Skips turns with null tokens
    # (human sessions, or crashed turns before usage was recorded).
    per_turn_totals = [
        (t.get("input_tokens") or 0) + (t.get("output_tokens") or 0)
        for t in turns
        if t.get("input_tokens") is not None or t.get("output_tokens") is not None
    ]
    tokens_per_turn_series: list[tuple[int, int]] = [
        (t["turn"], (t.get("input_tokens") or 0) + (t.get("output_tokens") or 0))
        for t in turns
        if t.get("input_tokens") is not None or t.get("output_tokens") is not None
    ]

    def _percentile(values: list[int], pct: float) -> float | None:
        if not values:
            return None
        s = sorted(values)
        k = max(0, min(len(s) - 1, int(round((pct / 100.0) * (len(s) - 1)))))
        return float(s[k])

    if per_turn_totals:
        mean_tokens_per_turn: float | None = sum(per_turn_totals) / len(per_turn_totals)
        median_tokens_per_turn = _percentile(per_turn_totals, 50)
        p90_tokens_per_turn = _percentile(per_turn_totals, 90)
    else:
        mean_tokens_per_turn = median_tokens_per_turn = p90_tokens_per_turn = None

    # --- Thinking intensity (proxy via thinking_chars; see logger.py) ---
    thinking_chars_series = [t.get("thinking_chars") or 0 for t in turns]
    thinking_turns = [c for c in thinking_chars_series if c > 0]
    if thinking_turns:
        mean_thinking_chars_per_turn: float | None = sum(thinking_turns) / len(thinking_turns)
        thinking_turn_fraction: float | None = len(thinking_turns) / total_turns if total_turns else None
    else:
        mean_thinking_chars_per_turn = None
        thinking_turn_fraction = 0.0 if total_turns else None

    # --- Tool usage ---
    all_tool_calls = []
    for t in turns:
        for tc in (t.get("tool_calls") or []):
            all_tool_calls.append(tc)

    tool_usage_breakdown = Counter(
        tc.get("name", "unknown") for tc in all_tool_calls
    )
    tool_calls_per_turn = len(all_tool_calls) / total_turns if total_turns > 0 else 0.0

    # --- Phantom rooms ---
    phantom_rooms: list[str] = summary.get("phantom_rooms") or []

    # --- Treasures (roadmap item #3) ---
    # Two metrics, two puzzles: "found" (took with `take`) and "deposited"
    # (put in trophy case despite Zork's tight carry limit). Prefer summary
    # aggregates when present; fall back to detection over (command, output)
    # so old session files still produce numbers without re-running.
    treasures_found: list[str] = summary.get("treasures_found") or []
    treasures_deposited: list[str] = summary.get("treasures_deposited") or []
    if not treasures_found and not treasures_deposited and turns:
        try:
            from zork_harness.treasures import find_treasure_events  # noqa: PLC0415
        except ImportError:
            find_treasure_events = None  # type: ignore[assignment]
        if find_treasure_events is not None:
            found_set, deposited_set = find_treasure_events(turns)
            treasures_found = sorted(found_set)
            treasures_deposited = sorted(deposited_set)

    return {
        # Identity
        "model": model_nickname,
        "map_mode": map_mode,
        "model_full": header.get("model", ""),
        "backend": header.get("backend", ""),
        "game": header.get("game", ""),
        "started_at": header.get("started_at", ""),
        "session_file": str(session["path"]),
        "player_type": header.get("player_type")
                       or ("human" if header.get("backend") == "human" else "llm"),
        # Scores
        "final_score": final_score,
        "max_score": max_score,
        "score_progression": score_progression,
        # Rooms
        "unique_rooms": unique_rooms,
        "room_discovery_curve": room_discovery_curve,
        # Deaths
        "total_deaths": total_deaths,
        "total_turns": total_turns,
        "death_rate": death_rate,
        "mean_turns_between_deaths": mean_turns_between_deaths,
        # Tokens
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_tokens": total_tokens,
        "tokens_per_room": tokens_per_room,
        "tokens_per_score_point": tokens_per_score_point,
        "mean_tokens_per_turn": mean_tokens_per_turn,
        "median_tokens_per_turn": median_tokens_per_turn,
        "p90_tokens_per_turn": p90_tokens_per_turn,
        "tokens_per_turn_series": tokens_per_turn_series,
        # Thinking (proxy via thinking_chars)
        "mean_thinking_chars_per_turn": mean_thinking_chars_per_turn,
        "thinking_turn_fraction": thinking_turn_fraction,
        # Tools
        "tool_calls_per_turn": tool_calls_per_turn,
        "tool_usage_breakdown": tool_usage_breakdown,
        # Malformed
        "malformed_turns": malformed_turns,
        "malformed_tokens": malformed_tokens,
        # Misc
        "phantom_rooms": phantom_rooms,
        "phantom_room_count": len(phantom_rooms),
        # Treasures
        "treasures_found": treasures_found,
        "treasures_deposited": treasures_deposited,
        "treasures_found_count": len(treasures_found),
        "treasures_deposited_count": len(treasures_deposited),
    }


# ---------------------------------------------------------------------------
# Console table
# ---------------------------------------------------------------------------

MAP_MODE_ORDER = ["none", "explore", "full"]

def _format_tokens(n: int) -> str:
    if n == 0:
        return "N/A"
    return f"{n / 1000:.1f}K"


def _format_float(v: float | None, decimals: int = 2) -> str:
    if v is None:
        return "N/A"
    if math.isinf(v):
        return "inf"
    return f"{v:.{decimals}f}"


def print_console_table(metrics_list: list[dict[str, Any]]) -> None:
    """Print a model x map_mode matrix with Score, Rooms, Deaths, Tokens.

    Humans are excluded from this matrix because they have no map_mode and
    aren't a model. They get their own table via print_humans_table().
    """
    metrics_list = [m for m in metrics_list if m.get("player_type") != "human"]
    if not metrics_list:
        return

    # Gather unique models and map_modes in a stable order
    models = sorted({m["model"] for m in metrics_list})
    map_modes_present = {m["map_mode"] for m in metrics_list}
    map_modes = [mm for mm in MAP_MODE_ORDER if mm in map_modes_present]
    map_modes += sorted(map_modes_present - set(MAP_MODE_ORDER))

    # Build lookup: (model, map_mode) -> metrics
    lookup: dict[tuple[str, str], dict] = {}
    for m in metrics_list:
        lookup[(m["model"], m["map_mode"])] = m

    # Column widths
    model_col_w = max(len("Model"), max(len(m) for m in models))
    map_col_w = max(len(mm) for mm in map_modes) if map_modes else 7
    # Per-map-mode cell carries: Score Rooms Deaths Malfrm Tokens Found Depos
    cell_w = 49

    # Header row 1: map_modes
    header1 = f"{'Model':<{model_col_w}}"
    for mm in map_modes:
        header1 += f"  {mm:^{cell_w}}"
    print()
    print(header1)

    # Header row 2: metric labels
    header2 = " " * model_col_w
    for _ in map_modes:
        header2 += (f"  {'Score':>6} {'Rooms':>5} {'Deaths':>6} "
                    f"{'Malfrm':>6} {'Tokens':>8} {'Found':>5} {'Depos':>5}")
    print(header2)

    # Separator
    total_width = model_col_w + len(map_modes) * (2 + cell_w)
    print("-" * total_width)

    # Data rows
    for model in models:
        row = f"{model:<{model_col_w}}"
        for mm in map_modes:
            m = lookup.get((model, mm))
            if m is None:
                row += f"  {'—':>6} {'—':>5} {'—':>6} {'—':>6} {'—':>8} {'—':>5} {'—':>5}"
            else:
                score = m["final_score"] if m["final_score"] is not None else "—"
                rooms = m["unique_rooms"] if m["unique_rooms"] is not None else "—"
                deaths = m["total_deaths"]
                malformed = m["malformed_turns"]
                tokens = _format_tokens(m["total_tokens"])
                # Found = took with `take`; Depos = placed in trophy case.
                # The gap between them is the inventory-management puzzle.
                found = m["treasures_found_count"]
                depos = m["treasures_deposited_count"]
                row += (f"  {str(score):>6} {str(rooms):>5} {str(deaths):>6} "
                        f"{str(malformed):>6} {tokens:>8} {found:>5} {depos:>5}")
        print(row)

    print()


def print_humans_table(metrics_list: list[dict[str, Any]]) -> None:
    """Print a flat table of human playthroughs ranked by max score.

    Humans don't fit the model x map_mode matrix (no map_mode, not a model),
    so they get their own section. Mirrors the layout used by leaderboard.py
    so the two tools agree.
    """
    humans = [m for m in metrics_list if m.get("player_type") == "human"]
    if not humans:
        return

    humans.sort(key=lambda m: -(m["max_score"] or 0))

    print()
    print("Humans")
    header = (f"{'Player':<8} {'Turns':>6} {'MaxScore':>9} {'Rooms':>6} "
              f"{'Found':>6} {'Deposit':>8}  Session")
    print(header)
    print("-" * len(header))
    for i, m in enumerate(humans, start=1):
        # Pull session timestamp out of the path for the trailing label.
        session_stem = Path(m["session_file"]).stem
        print(
            f"{'human ' + str(i):<8} "
            f"{m['total_turns']:>6} "
            f"{(m['max_score'] or 0):>9} "
            f"{m['unique_rooms']:>6} "
            f"{m['treasures_found_count']:>6} "
            f"{m['treasures_deposited_count']:>8}  "
            f"{session_stem}"
        )
    print()


# ---------------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------------

def write_csv(metrics_list: list[dict[str, Any]], output_path: Path) -> None:
    """Write one row per session with all scalar metrics to a CSV file."""
    if not metrics_list:
        return

    scalar_fields = [
        "model", "map_mode", "model_full", "backend", "game", "started_at",
        "session_file", "final_score", "max_score", "unique_rooms",
        "total_deaths", "total_turns", "death_rate", "mean_turns_between_deaths",
        "total_input_tokens", "total_output_tokens", "total_tokens",
        "tokens_per_room", "tokens_per_score_point",
        "mean_tokens_per_turn", "median_tokens_per_turn", "p90_tokens_per_turn",
        "mean_thinking_chars_per_turn", "thinking_turn_fraction",
        "tool_calls_per_turn", "malformed_turns", "malformed_tokens",
        "phantom_room_count",
        "treasures_found_count", "treasures_deposited_count",
    ]

    # Add one column per tool type seen across all sessions
    all_tool_names: set[str] = set()
    for m in metrics_list:
        all_tool_names.update(m["tool_usage_breakdown"].keys())
    tool_cols = sorted(all_tool_names)

    fieldnames = scalar_fields + [f"tool_{t}" for t in tool_cols]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for m in metrics_list:
            row: dict[str, Any] = {f: m.get(f, "") for f in scalar_fields}
            for tool_name in tool_cols:
                row[f"tool_{tool_name}"] = m["tool_usage_breakdown"].get(tool_name, 0)
            # Replace inf with empty string for cleaner CSV
            for k, v in row.items():
                if isinstance(v, float) and math.isinf(v):
                    row[k] = ""
            writer.writerow(row)


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def _get_model_colors(models: list[str]) -> dict[str, Any]:
    """Return a stable color mapping for models using matplotlib's tab10 palette."""
    import matplotlib.pyplot as plt  # noqa: PLC0415
    prop_cycle = plt.rcParams["axes.prop_cycle"]
    colors = [item["color"] for item in prop_cycle]
    return {model: colors[i % len(colors)] for i, model in enumerate(sorted(models))}


def _get_map_mode_hatches() -> dict[str, str]:
    return {"none": "", "explore": "//", "full": "xx"}


def plot_score_progression(
    metrics_list: list[dict[str, Any]],
    output_path: Path,
) -> None:
    """1x3 subplots (one per map_mode): score over turns, one line per model.

    Humans are excluded from this chart (they have no map_mode and their
    session names blow up the legend). Adding them as dashed baselines is
    roadmap item #4.
    """
    import matplotlib.pyplot as plt  # noqa: PLC0415

    metrics_list = [m for m in metrics_list if m.get("player_type") != "human"]
    if not metrics_list:
        return

    map_modes_present = {m["map_mode"] for m in metrics_list}
    map_modes = [mm for mm in MAP_MODE_ORDER if mm in map_modes_present]
    map_modes += sorted(map_modes_present - set(MAP_MODE_ORDER))

    models = sorted({m["model"] for m in metrics_list})
    colors = _get_model_colors(models)

    fig, axes = plt.subplots(1, len(map_modes), figsize=(6 * len(map_modes), 5), sharey=False)
    if len(map_modes) == 1:
        axes = [axes]

    for ax, mm in zip(axes, map_modes):
        ax.set_title(f"Map mode: {mm}")
        ax.set_xlabel("Turn")
        ax.set_ylabel("Score")
        ax.grid(True, alpha=0.3)

        for m in metrics_list:
            if m["map_mode"] != mm:
                continue
            prog = m["score_progression"]
            if not prog:
                continue
            turns_x = [p[0] for p in prog]
            scores_y = [p[1] for p in prog]
            ax.step(turns_x, scores_y, where="post",
                    label=m["model"], color=colors[m["model"]], linewidth=2)

        handles = [
            plt.Line2D([0], [0], color=colors[model], linewidth=2, label=model)
            for model in models
        ]
        ax.legend(handles=handles, fontsize=8)

    fig.suptitle("Score Progression by Map Mode", fontsize=14)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def plot_room_discovery(
    metrics_list: list[dict[str, Any]],
    output_path: Path,
) -> None:
    """1x3 subplots (one per map_mode): cumulative unique rooms over turns.

    Humans excluded for the same reason as plot_score_progression.
    """
    import matplotlib.pyplot as plt  # noqa: PLC0415

    metrics_list = [m for m in metrics_list if m.get("player_type") != "human"]
    if not metrics_list:
        return

    map_modes_present = {m["map_mode"] for m in metrics_list}
    map_modes = [mm for mm in MAP_MODE_ORDER if mm in map_modes_present]
    map_modes += sorted(map_modes_present - set(MAP_MODE_ORDER))

    models = sorted({m["model"] for m in metrics_list})
    colors = _get_model_colors(models)

    fig, axes = plt.subplots(1, len(map_modes), figsize=(6 * len(map_modes), 5), sharey=False)
    if len(map_modes) == 1:
        axes = [axes]

    for ax, mm in zip(axes, map_modes):
        ax.set_title(f"Map mode: {mm}")
        ax.set_xlabel("Turn")
        ax.set_ylabel("Cumulative Unique Rooms")
        ax.grid(True, alpha=0.3)

        for m in metrics_list:
            if m["map_mode"] != mm:
                continue
            curve = m["room_discovery_curve"]
            if not curve:
                continue
            turns_x = [p[0] for p in curve]
            rooms_y = [p[1] for p in curve]
            ax.plot(turns_x, rooms_y, label=m["model"],
                    color=colors[m["model"]], linewidth=2)

        handles = [
            plt.Line2D([0], [0], color=colors[model], linewidth=2, label=model)
            for model in models
        ]
        ax.legend(handles=handles, fontsize=8)

    fig.suptitle("Room Discovery Curve by Map Mode", fontsize=14)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def plot_tokens_per_turn(
    metrics_list: list[dict[str, Any]],
    output_path: Path,
) -> None:
    """1x3 subplots (one per map_mode): per-turn total tokens over time, one line per model.

    A coarse "compute-per-decision" signal, useful for spotting models that
    front-load reasoning on specific turns vs. ones that spend uniformly.
    Skips sessions with no token data (e.g. human play, hence no human filter
    needed; the empty-series check handles them naturally).
    """
    import matplotlib.pyplot as plt  # noqa: PLC0415

    # Filter to sessions that actually have per-turn token data
    has_data = [m for m in metrics_list if m.get("tokens_per_turn_series")]
    if not has_data:
        return

    map_modes_present = {m["map_mode"] for m in has_data}
    map_modes = [mm for mm in MAP_MODE_ORDER if mm in map_modes_present]
    map_modes += sorted(map_modes_present - set(MAP_MODE_ORDER))

    models = sorted({m["model"] for m in has_data})
    colors = _get_model_colors(models)

    fig, axes = plt.subplots(1, len(map_modes), figsize=(6 * len(map_modes), 5), sharey=False)
    if len(map_modes) == 1:
        axes = [axes]

    for ax, mm in zip(axes, map_modes):
        ax.set_title(f"Map mode: {mm}")
        ax.set_xlabel("Turn")
        ax.set_ylabel("Tokens spent (input + output)")
        ax.grid(True, alpha=0.3)

        for m in has_data:
            if m["map_mode"] != mm:
                continue
            series = m["tokens_per_turn_series"]
            if not series:
                continue
            turns_x = [p[0] for p in series]
            tokens_y = [p[1] for p in series]
            ax.plot(turns_x, tokens_y, label=m["model"],
                    color=colors[m["model"]], linewidth=1.5, alpha=0.8)

        handles = [
            plt.Line2D([0], [0], color=colors[model], linewidth=2, label=model)
            for model in models
        ]
        ax.legend(handles=handles, fontsize=8)

    fig.suptitle("Tokens per Turn by Map Mode", fontsize=14)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def plot_model_comparison(
    metrics_list: list[dict[str, Any]],
    output_path: Path,
) -> None:
    """Grouped bar chart: 2 subplots (final_score, unique_rooms), bars grouped by model, colored by map_mode.

    Humans are excluded; their per-session 'model_nickname' is the session
    timestamp (since they have no model name) and that blows up the x-axis.
    Adding humans as a separate aggregated bar group is roadmap item #4.
    """
    import matplotlib.pyplot as plt  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    metrics_list = [m for m in metrics_list if m.get("player_type") != "human"]
    if not metrics_list:
        return

    map_modes_present = {m["map_mode"] for m in metrics_list}
    map_modes = [mm for mm in MAP_MODE_ORDER if mm in map_modes_present]
    map_modes += sorted(map_modes_present - set(MAP_MODE_ORDER))

    models = sorted({m["model"] for m in metrics_list})
    lookup: dict[tuple[str, str], dict] = {
        (m["model"], m["map_mode"]): m for m in metrics_list
    }

    # Stable colors per map_mode
    mm_colors = {"none": "#4c72b0", "explore": "#55a868", "full": "#c44e52"}
    default_colors = ["#8172b2", "#ccb974", "#64b5cd"]
    for i, mm in enumerate(map_modes):
        if mm not in mm_colors:
            mm_colors[mm] = default_colors[i % len(default_colors)]

    n_models = len(models)
    n_modes = len(map_modes)
    bar_width = 0.8 / n_modes
    x = np.arange(n_models)

    fig, (ax_score, ax_rooms) = plt.subplots(1, 2, figsize=(12, 5))

    for i, mm in enumerate(map_modes):
        offset = (i - n_modes / 2 + 0.5) * bar_width
        scores = []
        rooms = []
        for model in models:
            m = lookup.get((model, mm))
            scores.append(m["final_score"] or 0 if m else 0)
            rooms.append(m["unique_rooms"] or 0 if m else 0)

        ax_score.bar(x + offset, scores, bar_width, label=mm, color=mm_colors[mm], alpha=0.85)
        ax_rooms.bar(x + offset, rooms, bar_width, label=mm, color=mm_colors[mm], alpha=0.85)

    for ax, ylabel, title in [
        (ax_score, "Final Score", "Final Score by Model & Map Mode"),
        (ax_rooms, "Unique Rooms", "Rooms Visited by Model & Map Mode"),
    ]:
        ax.set_xticks(x)
        ax.set_xticklabels(models, rotation=15, ha="right", fontsize=9)
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.legend(title="Map mode", fontsize=8)
        ax.grid(True, axis="y", alpha=0.3)

    fig.suptitle("Model Comparison", fontsize=14)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze zork-harness benchmark JSONL session logs."
    )
    parser.add_argument(
        "--results-dir",
        default=None,
        help="Path to benchmark/results/ directory. Defaults to benchmark/results/ relative to this script.",
    )
    args = parser.parse_args()

    if args.results_dir is not None:
        results_dir = Path(args.results_dir)
    else:
        results_dir = Path(__file__).parent / "results"

    if not results_dir.exists():
        print(f"Results directory not found: {results_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading sessions from: {results_dir}")
    sessions = load_all_sessions(results_dir)

    if not sessions:
        print("No session_*.jsonl files found.", file=sys.stderr)
        sys.exit(0)

    print(f"Found {len(sessions)} session(s).")

    metrics_list = [compute_metrics(s) for s in sessions]

    # --- Console tables (AI matrix + Humans flat) ---
    print_console_table(metrics_list)
    print_humans_table(metrics_list)

    # --- CSV ---
    csv_path = results_dir / "benchmark_results.csv"
    write_csv(metrics_list, csv_path)
    print(f"CSV written to: {csv_path}")

    # --- Charts (optional) ---
    try:
        import matplotlib  # noqa: F401
        import numpy  # noqa: F401
    except ImportError:
        print("matplotlib or numpy not installed — skipping chart generation.")
        return

    score_png = results_dir / "score_progression.png"
    room_png = results_dir / "room_discovery.png"
    tokens_png = results_dir / "tokens_per_turn.png"
    comparison_png = results_dir / "model_comparison.png"

    plot_score_progression(metrics_list, score_png)
    print(f"Chart written to: {score_png}")

    plot_room_discovery(metrics_list, room_png)
    print(f"Chart written to: {room_png}")

    plot_tokens_per_turn(metrics_list, tokens_png)
    print(f"Chart written to: {tokens_png}")

    plot_model_comparison(metrics_list, comparison_png)
    print(f"Chart written to: {comparison_png}")


if __name__ == "__main__":
    main()
