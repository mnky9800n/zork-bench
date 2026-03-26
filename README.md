# zork-bench

A harness for evaluating LLM reasoning by having them play 1970s text adventure games, starting with Zork I.

LLMs are bad at text adventures ([arxiv.org/abs/2602.15867](https://arxiv.org/abs/2602.15867)). Solving text adventures requires spatial reasoning, long-horizon planning, state tracking, and common-sense inference, the same capabilities the AI industry is spending billions trying to achieve. This project provides the infrastructure to measure and improve those capabilities.

Standard LLM benchmarks measure component skills in isolation. Text adventures measure whether those skills compose into coherent agent behavior over extended interactions. The gap between a model's component scores and its gameplay performance reveals how well it integrates reasoning, memory, and planning which is the core unsolved problem in building capable AI agents.

## How it works

An LLM plays Zork through a game session running in Docker (dfrotz + Infocom game files). The harness manages the game I/O, provides tools the LLM can use (self-built map, inventory tracking, notes), and logs everything for analysis.

```
LLM (Claude API)
  |
  |-- tool calls: record_room, find_path, update_inventory, add_note
  |-- game command: "go north", "take lamp", etc.
  |
  v
Harness (zork_harness)
  |
  v
Docker container (dfrotz + game files)
```

The LLM builds its own map as it explores. It has no pre-loaded knowledge of the game world. It discovers rooms, records exits, tracks inventory, and takes notes -- all through tool use.

## Setup

Requires Docker and Python 3.12+.

```bash
# Build the game container
docker build -t zork-harness-game .

# Install dependencies
uv sync

# Set your API key
export ANTHROPIC_API_KEY=your-key-here
```

## Usage

```bash
# Basic run
uv run zork-harness --game zork1 --model claude-sonnet-4-6

# With extended thinking
uv run zork-harness --game zork1 --model claude-opus-4-6 --thinking

# With fixed thinking budget
uv run zork-harness --game zork1 --model claude-opus-4-6 --budget-tokens 32000

# With the live viewer (map + game log GUI)
uv run zork-harness --game zork1 --model claude-sonnet-4-6 --frontend

# Limit turns
uv run zork-harness --game zork1 --max-turns 50 --frontend
```

### Options

| Flag | Description |
|------|-------------|
| `--game` | Which game to play (default: `zork1`). Supports 40 Infocom titles. |
| `--model` | Anthropic model ID (default: `claude-sonnet-4-6`). |
| `--max-turns` | Maximum turns before stopping (default: 200). |
| `--thinking` | Enable adaptive extended thinking. |
| `--budget-tokens N` | Enable fixed-budget thinking with N tokens. |
| `--frontend` | Open the live viewer window (split-pane map + game log). |
| `--session-dir` | Directory for session logs (default: `sessions/`). |

## Live viewer

The `--frontend` flag opens a split-pane GUI:

- **Left panel**: Zoomed map of Zork I that auto-pans to follow the LLM. Blue dots mark previously visited rooms. A robot emoji marks the current position. Click and drag to pan freely; double-click to snap back to following the LLM.
- **Right panel**: Scrolling game log showing the LLM's thinking, tool use (map recording, pathfinding, inventory), commands, and game output -- all color-coded.

## LLM tools

The LLM builds its own map from scratch as it explores. No pre-loaded map is provided.

| Tool | Purpose |
|------|---------|
| `record_room(room_name, exits, items)` | Save a visited room's exits and items to the map. Merges with existing data on revisit. |
| `look_up_room(room_name)` | Retrieve recorded data for a room. |
| `list_known_rooms()` | List all rooms recorded so far. |
| `find_path(from_room, to_room)` | BFS pathfinding over the self-built map. |
| `update_inventory(action, item)` | Track items picked up or dropped. |
| `add_note(note)` | Free-form scratchpad for puzzle clues, observations, etc. |

## Metrics

### Game performance (zork-bench)

These are measured directly from gameplay:

| Metric | Description |
|--------|-------------|
| Rooms discovered | Number of unique rooms visited (out of ~40 in Zork I) |
| Treasures collected | Number of treasures brought to the trophy case (out of 19) |
| Score achieved | Game score (out of 350) |
| Turns to first death | How long the LLM survives |
| Turns to first treasure | How quickly it finds and collects a treasure |
| Tool usage efficiency | Map lookups and pathfinding vs. aimless wandering |

### Component skill evals (via lm-eval-harness)

These standard benchmarks measure the individual reasoning skills that text adventures require. The gap between component scores and actual gameplay performance is the interesting finding.

**Tier 1 -- Directly relevant:**

| Eval | Skill tested | Why it matters for Zork |
|------|-------------|------------------------|
| BBH Navigate | Spatial reasoning | Following directions, tracking position |
| Mastermind | Iterative deduction from feedback | Puzzle solving with incomplete information |
| bAbIlong qa19 | Path finding | Route planning through connected rooms |
| bAbIlong qa17 | Positional reasoning | Tracking where things are |
| GraphWalks | Multi-hop graph reasoning | Reasoning over room connections |
| DROP | Discrete reasoning in context | Logic puzzles in adventure games |

**Tier 2 -- Strong complementary:**

| Eval | Skill tested | Why it matters for Zork |
|------|-------------|------------------------|
| LogiQA 2.0 | Logical deduction | Puzzle solving |
| bAbI full suite | Fact chaining, state tracking | Prerequisite reasoning skills |
| LongBench2 Agent History | Multi-turn agent comprehension | Game session memory |
| CommonsenseQA | Everyday common sense | "Lamp needs fuel" type knowledge |
| PIQA | Physical interaction reasoning | "Can I cut rope with a sword?" |
| HellaSwag | Action sequence prediction | Predicting consequences |

**Tier 3 -- Nice to have:**

| Eval | Skill tested |
|------|-------------|
| WinoGrande | Reference resolution |
| ARC Challenge | Science/world knowledge |
| IFEval | Instruction following |

## Session logs

Each run produces two files in `sessions/`:

- `session_<timestamp>.jsonl` -- Machine-readable log. One JSON object per turn with command, output, tool calls, thinking, room, and timestamp. Final line is a session summary with rooms visited, unique room count, and room visit sequence.
- `session_<timestamp>.txt` -- Human-readable transcript with full thinking, tool use, commands, game output, and a session summary at the end.

## Supported games

The Docker image includes 40 Infocom titles. Pass the game key to `--game`:

`abyss`, `amfv`, `arthur`, `ballyhoo`, `beyondzork`, `borderzone`, `bureaucracy`, `cutthroats`, `deadline`, `enchanter`, `hitchhiker`, `hollywoodhijinx`, `infidel`, `journey`, `leathergoddesses`, `lurkinghorror`, `minizork`, `minizork2`, `moonmist`, `nordandbert`, `planetfall`, `plunderedhearts`, `restaurant`, `seastalker`, `sherlock`, `sherlock-nosound`, `shogun`, `sorcerer`, `spellbreaker`, `starcross`, `stationfall`, `suspect`, `suspended`, `trinity`, `wishbringer`, `witness`, `zork0`, `zork1`, `zork2`, `zork3`

## Project structure

```
zork-bench/
  Dockerfile                    # Game container (dfrotz + 40 Infocom games)
  pyproject.toml                # uv project config
  zork-1-map-ZUG-1982.jpeg      # Zork I map (used by the viewer)
  papers/                       # Reference papers
  sessions/                     # Session logs (gitignored)
  src/zork_harness/
    agent.py                    # LLM agent loop (Anthropic SDK + tool use)
    session.py                  # Game I/O via pexpect to Docker
    tools.py                    # Self-built map, inventory, notes
    map_data.py                 # Static Zork I map (reference, not used by LLM)
    map_coords.py               # Room pixel coordinates for the map viewer
    map_viewer.py               # Live tkinter viewer (map + game log)
    logger.py                   # JSONL + text session logging
```
