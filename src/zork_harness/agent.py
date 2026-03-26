"""LLM agent loop: plays Zork by driving a ZorkSession through the Anthropic API."""

import argparse
import re
import sys
import threading

import anthropic

from zork_harness.logger import SessionLogger
from zork_harness.session import GAMES, ZorkSession
from zork_harness.tools import ToolRegistry

_BASE_PROMPT = """\
You are playing Zork, a classic text adventure game. Your goal is to explore the world, \
collect treasures, solve puzzles, and maximize your score.

Rules:
- Use short, imperative commands: "go north", "take lamp", "open mailbox", "look", "inventory".
- Do not use elaborate sentences. The game parser only understands simple commands.
- Think briefly, then issue exactly ONE game command per turn.
- Your final line MUST be the command on its own line, prefixed with "> ".
"""

_MAP_EXPLORE_PROMPT = """
You have tools to build your own map as you explore. There is no pre-loaded map; \
you discover the world by playing and recording what you find.

Map tools:
- record_room(room_name, exits, items): After entering a new room, call this to save \
what you learned. Pass the room name exactly as the game prints it, a dict of visible exits \
mapping direction to the destination room name (use the destination name only if you already \
know it, otherwise omit that exit until you visit), and a list of notable items. \
Revisiting a room updates and merges the existing entry.
- look_up_room(room_name): Retrieve the exits and items you recorded for a room.
- list_known_rooms(): See every room you have recorded so far with their known exits.
- find_path(from_room, to_room): Compute a route between two recorded rooms using BFS \
over your self-built map. Returns the sequence of direction/room steps to follow.

After each new room description, call record_room before deciding what to do next.
Use find_path when you need to return to a room you have already visited.
"""

_MAP_FULL_PROMPT = """
You have a complete map of the game pre-loaded. You can query it at any time.

Map tools:
- look_up_room(room_name): Look up any room's exits and items.
- list_known_rooms(): See the full map with all rooms and exits.
- find_path(from_room, to_room): Compute a route between any two rooms using BFS.
- record_room(room_name, exits, items): Update or correct map data based on what you observe.

Use look_up_room and find_path to plan efficient routes. The map may not be 100% complete, \
so record_room when you discover exits or items not in the pre-loaded data.
"""

_MAP_NONE_PROMPT = """
You have no map. You must rely entirely on your memory and reasoning to navigate.
"""

_TOOLS_PROMPT = """
Other tools:
- update_inventory(action, item): Track items you pick up ("add") or drop ("remove").
- add_note(note): Record any observation, puzzle clue, or reminder for yourself.
"""

_EXAMPLE_PROMPT = """
Example turn:
I am in the Living Room. I can see exits north and east. There is a sword here.
I should grab the sword and head north.
> take sword
"""


def _build_system_prompt(map_mode: str) -> str:
    parts = [_BASE_PROMPT]
    if map_mode == "explore":
        parts.append(_MAP_EXPLORE_PROMPT)
    elif map_mode == "full":
        parts.append(_MAP_FULL_PROMPT)
    else:
        parts.append(_MAP_NONE_PROMPT)
    parts.append(_TOOLS_PROMPT)
    parts.append(_EXAMPLE_PROMPT)
    return "\n".join(parts)

_COMMAND_RE = re.compile(r"^>\s*(.+)$", re.MULTILINE)


def _extract_command(text: str) -> str | None:
    """Extract the last "> command" line from the model's text response."""
    matches = _COMMAND_RE.findall(text)
    if not matches:
        return None
    return matches[-1].strip()


def _extract_thinking(response) -> str | None:
    """Extract thinking text from response content blocks."""
    for block in response.content:
        if block.type == "thinking" and hasattr(block, "thinking"):
            return block.thinking
    return None


_NON_ROOM_PATTERNS = [
    "score",
    "move",
    "rank",
    "total",
    "opening",
    "you ",
    "there ",
    "it ",
    "the ",
    "a ",
    "your ",
    "taken",
    "dropped",
    "done",
    "ok",
    "i don't",
    "what",
    "which",
    "that",
    "nothing",
    "with",
    "using",
]


def _detect_room(game_output: str) -> str | None:
    """Try to extract the room name from game output.

    Frotz prints the room name as the first non-blank line when entering a room.
    Room names are short, title-case, and don't end with punctuation.
    """
    for line in game_output.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Room names are short, don't end with sentence punctuation
        if len(line) > 50:
            break
        if line.endswith((".","!","?",":")):
            break
        if line.startswith(("[", "(", ">")):
            break
        # Filter out common non-room output
        lower = line.lower()
        if any(lower.startswith(p) for p in _NON_ROOM_PATTERNS):
            break
        # Room names have at least one capital letter and no leading lowercase
        if line[0].islower():
            break
        return line
    return None


def run_agent(
    game: str,
    model: str,
    max_turns: int,
    session_dir: str,
    thinking: bool = False,
    budget_tokens: int = 0,
    viewer=None,
    map_mode: str = "explore",
) -> None:
    client = anthropic.Anthropic()
    registry = ToolRegistry(map_mode=map_mode)
    system_prompt = _build_system_prompt(map_mode)
    tool_schemas = registry.get_schemas()
    logger = SessionLogger(session_dir, game=game, model=model)

    print(f"Starting game: {game}")
    print(f"Model: {model} (thinking: {'adaptive' if thinking else 'off'}, map: {map_mode})")
    print(f"Session log: {logger.txt_path}")

    session = ZorkSession(game)
    opening_text = session.start()
    print(opening_text)
    print()

    # Detect starting room from opening text
    opening_room = _detect_room(opening_text)
    if viewer and opening_room:
        viewer.set_room(opening_room)

    # The conversation history sent to the API each turn
    messages: list[dict] = [
        {"role": "user", "content": opening_text},
    ]

    for turn in range(1, max_turns + 1):
        tool_calls_this_turn: list[dict] = []
        thinking_text = None

        # Inner loop: handle tool use until we get a plain text response
        while True:
            api_kwargs = dict(
                model=model,
                max_tokens=budget_tokens + 4096 if budget_tokens else 1024,
                system=system_prompt,
                tools=tool_schemas,
                messages=messages,
            )
            if thinking:
                if budget_tokens:
                    api_kwargs["thinking"] = {
                        "type": "enabled",
                        "budget_tokens": budget_tokens,
                    }
                else:
                    api_kwargs["thinking"] = {"type": "adaptive"}
                # Adaptive/enabled thinking needs higher max_tokens
                api_kwargs["max_tokens"] = max(api_kwargs["max_tokens"], 8192)

            # Use streaming to avoid timeout on long thinking requests
            with client.messages.stream(**api_kwargs) as stream:
                response = stream.get_final_message()

            # Capture thinking from this response
            turn_thinking = _extract_thinking(response)
            if turn_thinking:
                thinking_text = turn_thinking

            # Append the assistant's response to the conversation
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    result = registry.execute(block.name, block.input)
                    tc = {"name": block.name, "input": block.input, "result": result}
                    tool_calls_this_turn.append(tc)
                    # Print tool use to terminal immediately
                    print(f"[{turn}] tool: {block.name}({block.input}) => {result[:200]}")
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        }
                    )
                messages.append({"role": "user", "content": tool_results})
                continue  # let the model respond to the tool results

            # stop_reason == "end_turn": extract the command from text blocks
            text = "".join(
                block.text for block in response.content if hasattr(block, "text")
            )
            break

        command = _extract_command(text)
        if command is None:
            print(f"[turn {turn}] Could not parse a command from model response:")
            print(text)
            print("[Stopping]")
            break

        game_output = session.send_command(command)
        room = _detect_room(game_output)

        # Update live map viewer
        if viewer:
            if room:
                viewer.set_room(room)
            viewer.log(
                turn=turn,
                command=command,
                output=game_output,
                thinking=thinking_text,
                reasoning=text,
                room=room,
                tool_calls=tool_calls_this_turn,
            )

        logger.log_turn(
            turn=turn,
            command=command,
            output=game_output,
            tool_calls=tool_calls_this_turn,
            thinking=thinking_text,
            reasoning=text,
            room=room,
        )

        # Print turn output
        if thinking_text:
            # Show a truncated version of thinking in terminal
            preview = thinking_text[:200]
            if len(thinking_text) > 200:
                preview += f"... ({len(thinking_text)} chars)"
            print(f"[{turn}] thinking: {preview}")
        if text.strip() != f"> {command}":
            # Show reasoning if there's more than just the command
            reasoning_lines = [l for l in text.strip().split("\n") if not l.startswith(">")]
            if reasoning_lines:
                print(f"[{turn}] reasoning: {' '.join(reasoning_lines)[:200]}")
        print(f"[{turn}] > {command}")
        if room:
            print(f"[{turn}] room: {room}")
        print(game_output)
        print()

        # Feed the game response back as the next user message
        messages.append({"role": "user", "content": game_output})

    session.close()
    logger.finalize()
    print(f"Session ended. Transcript: {logger.txt_path}")
    print(f"Session data: {logger.jsonl_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an LLM agent to play Zork.")
    parser.add_argument(
        "--game",
        default="zork1",
        choices=sorted(GAMES),
        help="Which game to play (default: zork1)",
    )
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-6",
        help="Anthropic model ID (default: claude-sonnet-4-6)",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=200,
        help="Maximum number of turns before stopping (default: 200)",
    )
    parser.add_argument(
        "--session-dir",
        default="sessions",
        help="Directory for session logs (default: sessions/)",
    )
    parser.add_argument(
        "--thinking",
        action="store_true",
        help="Enable adaptive thinking (no budget needed).",
    )
    parser.add_argument(
        "--budget-tokens",
        type=int,
        default=0,
        help="Thinking budget tokens. Implies --thinking with type=enabled. 0 uses adaptive (default: 0).",
    )
    parser.add_argument(
        "--frontend",
        action="store_true",
        help="Open the live viewer window (map + game log).",
    )
    parser.add_argument(
        "--map-mode",
        choices=["none", "explore", "full"],
        default="explore",
        help="Map mode: none (no map tools), explore (LLM builds its own map), full (pre-loaded complete map). Default: explore.",
    )
    args = parser.parse_args()

    # --budget-tokens implies thinking
    use_thinking = args.thinking or args.budget_tokens > 0

    viewer = None
    if args.frontend:
        from zork_harness.map_viewer import MapViewer

        viewer = MapViewer()

    def _run():
        try:
            run_agent(
                game=args.game,
                model=args.model,
                max_turns=args.max_turns,
                session_dir=args.session_dir,
                thinking=use_thinking,
                budget_tokens=args.budget_tokens,
                viewer=viewer,
                map_mode=args.map_mode,
            )
        except KeyboardInterrupt:
            pass
        finally:
            if viewer:
                viewer.close()

    if viewer:
        # tkinter must run on the main thread; agent runs in background
        agent_thread = threading.Thread(target=_run, daemon=True)
        agent_thread.start()
        try:
            viewer.run()
        except KeyboardInterrupt:
            print("\n[Interrupted]")
            sys.exit(0)
    else:
        try:
            _run()
        except KeyboardInterrupt:
            print("\n[Interrupted]")
            sys.exit(0)


if __name__ == "__main__":
    main()
