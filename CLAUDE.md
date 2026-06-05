# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

zork-bench: a harness for evaluating LLM reasoning by having them play 1970s Infocom text adventures (starting with Zork I). An LLM plays through a Docker container running bocfel (a Z-machine interpreter) over the RemGlk JSON protocol, with tools for self-built maps, inventory tracking, and pathfinding. Supports Fireworks, Anthropic, and OpenAI backends plus a human play mode.

## Commands

```bash
# Setup
docker build -t zork-harness-game .   # Build bocfel+remglk container (required first time; rebuild to pick up I/O changes)
uv sync                                # Install Python dependencies

# Run (requires at least one API key: FIREWORKS_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY)
uv run zork-harness --game zork1 --frontend                          # Fireworks (default)
uv run zork-harness --backend anthropic --thinking --frontend        # Anthropic with extended thinking
uv run zork-harness --backend openai --model gpt-4o --frontend       # OpenAI
uv run zork-harness --backend human --game zork1                     # Play yourself
uv run zork-harness --max-turns 20 --frontend                       # Quick test run

# Map calibration tool (for updating room pixel coordinates)
uv run python -m zork_harness.calibrate_map
```

There are no tests or linters configured.

## Architecture

Entry point is `zork_harness.agent:main()`, exposed as the `zork-harness` CLI command.

### Game loop (`agent.py`)

`run_agent()` orchestrates everything:
1. Creates a `ToolRegistry` (map state, inventory, notes) based on `--map-mode`
2. Spawns a `RemGlkSession` (JSON over a pipe to the Docker bocfel+remglk container)
3. Runs a turn loop: call LLM → handle tool calls in inner loop (up to 10 rounds) → extract game command (regex `^>\s*(.+)$`) → send to game → detect room → log → repeat
4. Two backend code paths: `_run_anthropic()` and `_run_openai()` (also used for Fireworks). Both return a normalized dict with `type`, `text`, `tool_calls`, `thinking`, `usage`.

### Tool system (`tools.py`)

Tools are defined once in a backend-neutral `_TOOL_DEFS` list, then converted at runtime via `get_anthropic_schemas()` or `get_openai_schemas()`. The `ToolRegistry` class holds all mutable game state (rooms dict, inventory list, notes list) and dispatches tool calls via `execute()`. Map tools (`record_room`, `look_up_room`, `list_known_rooms`, `find_path`) are conditionally available based on `--map-mode`; `update_inventory` and `add_note` are always available.

### Room tracking (`agent.py` — `RoomTracker`)

Handles Zork's ambiguous room names (multiple rooms called "Forest", maze rooms, etc.) with a 3-tier disambiguation: transition-based (prev_room + direction + raw_name), description-based (substring matching on game output), and direct mapping. Hardcoded dictionaries cover the maze extensively (~15 distinct maze rooms).

### Game I/O (`session.py`)

`RemGlkSession` (implements the `GameSession` ABC) talks to `docker run --rm -i zork-harness-game <game_file>` via `subprocess`, exchanging newline-delimited JSON over the RemGlk protocol instead of screen-scraping a terminal. It sends an `init` handshake, then a `line` input event per command, and reads `update` objects framed by `_decode_json_object` (accumulate chars until one object parses). Prose comes from buffer windows (`content` entries with `"text"`; the echoed command run styled `"input"` and the trailing `">"` are stripped); the status line comes from grid windows (`"lines"`), and `get_score()` reads the score off it via `SessionLogger._parse_score` (no `score` command is injected, so the move counter stays clean). Char-input prompts (e.g. a death "press any key") are auto-advanced. Window ids change every turn, so buffer-vs-grid is detected structurally and the next input's window/gen always come from the `input` array. The `GAMES` dict maps 40 game keys to ROM filenames. `GameSessionError` is raised on a dead process so the agent loop can terminate cleanly; the `GameSession` seam lets another interpreter (e.g. a future Rust Z-machine VM) drop in unchanged.

### Logging (`logger.py`)

Dual output per session: JSONL (machine-readable turn records with tool calls, rooms, scores) and TXT (human-readable transcript). Score detection via regex on game output.

### Live viewer (`map_viewer.py`)

Tkinter split-pane GUI: left panel shows the Zork I paper map with room markers (robot emoji for current, blue dots for visited), right panel shows color-coded game log. Auto-follows player position; click-drag to pan freely, double-click to snap back. Thread-safe (agent thread updates state, main thread renders). Room pixel coordinates come from `map_coords.py`.

### Map modes

- `none`: No map tools. Tests pure LLM spatial reasoning.
- `explore` (default): LLM builds its own map from scratch using tools.
- `full`: Pre-loaded complete map from `map_data.py`. Tests puzzle-solving in isolation.

The performance gap between modes is itself a metric for spatial reasoning capability.
