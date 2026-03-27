"""LLM agent loop: plays Zork by driving a ZorkSession through an LLM API."""

import argparse
import json
import os
import re
import sys
import threading

from zork_harness.logger import SessionLogger
from zork_harness.session import GAMES, ZorkSession
from zork_harness.tools import ToolRegistry, get_anthropic_schemas, get_openai_schemas

# ---------------------------------------------------------------------------
# System prompt fragments
# ---------------------------------------------------------------------------

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
    matches = _COMMAND_RE.findall(text)
    if not matches:
        return None
    return matches[-1].strip()


_NON_ROOM_PATTERNS = [
    "score", "move", "rank", "total", "opening",
    "you ", "there ", "it ", "the ", "a ", "your ",
    "taken", "dropped", "done", "ok",
    "i don't", "what", "which", "that", "nothing", "with", "using",
]


def _detect_room(game_output: str) -> str | None:
    for line in game_output.split("\n"):
        line = line.strip()
        if not line:
            continue
        if len(line) > 50:
            break
        if line.endswith((".", "!", "?", ":")):
            break
        if line.startswith(("[", "(", ">")):
            break
        lower = line.lower()
        if any(lower.startswith(p) for p in _NON_ROOM_PATTERNS):
            break
        if line[0].islower():
            break
        return line
    return None


# ---------------------------------------------------------------------------
# Anthropic backend
# ---------------------------------------------------------------------------

def _run_anthropic(client, model, system_prompt, tool_schemas, messages,
                   thinking, budget_tokens):
    """One API round-trip using the Anthropic SDK. Returns (response, text, tool_calls, thinking_text, usage)."""
    import anthropic as _anthropic

    api_kwargs = dict(
        model=model,
        max_tokens=budget_tokens + 4096 if budget_tokens else 1024,
        system=system_prompt,
        tools=tool_schemas,
        messages=messages,
    )
    if thinking:
        if budget_tokens:
            api_kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget_tokens}
        else:
            api_kwargs["thinking"] = {"type": "adaptive"}
        api_kwargs["max_tokens"] = max(api_kwargs["max_tokens"], 8192)

    with client.messages.stream(**api_kwargs) as stream:
        response = stream.get_final_message()

    # Extract usage
    usage = {"input": 0, "output": 0}
    if response.usage:
        usage["input"] = response.usage.input_tokens
        usage["output"] = response.usage.output_tokens

    # Extract thinking
    thinking_text = None
    for block in response.content:
        if block.type == "thinking" and hasattr(block, "thinking"):
            thinking_text = block.thinking
            break

    # Append assistant message
    messages.append({"role": "assistant", "content": response.content})

    # Handle tool use
    if response.stop_reason == "tool_use":
        tool_calls = []
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            tool_calls.append({"id": block.id, "name": block.name, "input": block.input})
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": None,  # filled by caller
            })
        return {"type": "tool_use", "tool_calls": tool_calls, "tool_results_template": tool_results,
                "thinking": thinking_text, "usage": usage}

    # Extract text
    text = "".join(block.text for block in response.content if hasattr(block, "text"))
    return {"type": "text", "text": text, "thinking": thinking_text, "usage": usage}


def _append_anthropic_tool_results(messages, tool_results):
    """Append tool results in Anthropic format."""
    messages.append({"role": "user", "content": tool_results})


# ---------------------------------------------------------------------------
# OpenAI/Fireworks backend
# ---------------------------------------------------------------------------

def _parse_json_tool_call(text: str) -> dict | None:
    """Try to parse a tool call from raw JSON in the model's text output.

    Some models (especially smaller ones) dump tool calls as JSON text
    instead of using the structured tool calling API.
    """
    text = text.strip()
    # Try to find JSON object in the text
    for start in range(len(text)):
        if text[start] == "{":
            for end in range(len(text), start, -1):
                if text[end - 1] == "}":
                    try:
                        data = json.loads(text[start:end])
                        # Check if it looks like a tool call
                        name = data.get("name") or data.get("function")
                        params = data.get("parameters") or data.get("arguments") or data.get("input")
                        if name and isinstance(params, dict):
                            return {"name": name, "input": params}
                    except json.JSONDecodeError:
                        continue
    return None


def _run_openai(client, model, system_prompt, tool_schemas, messages,
                thinking=False, **_kwargs):
    """One API round-trip using the OpenAI SDK. Always streams for compatibility."""
    usage = {"input": 0, "output": 0}
    api_messages = [{"role": "system", "content": system_prompt}] + messages

    extra_kwargs = {}
    if thinking:
        extra_kwargs["reasoning_effort"] = "high"

    max_tokens = 16384 if thinking else 2048

    sys.stdout.write("  [waiting for model...] ")
    sys.stdout.flush()

    stream = client.chat.completions.create(
        model=model,
        messages=api_messages,
        tools=tool_schemas if tool_schemas else None,
        max_tokens=max_tokens,
        stream=True,
        stream_options={"include_usage": True},
        **extra_kwargs,
    )

    collected_content = []
    collected_tool_calls: dict[int, dict] = {}
    usage_data = None
    reasoning_content_parts = []
    chunk_count = 0

    for chunk in stream:
        chunk_count += 1
        if chunk.usage:
            usage_data = chunk.usage
        for choice_delta in (chunk.choices or []):
            delta = choice_delta.delta
            if delta.content:
                collected_content.append(delta.content)
            if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                reasoning_content_parts.append(delta.reasoning_content)
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in collected_tool_calls:
                        collected_tool_calls[idx] = {
                            "id": tc_delta.id or "",
                            "name": (tc_delta.function.name
                                     if tc_delta.function and tc_delta.function.name else ""),
                            "arguments": "",
                        }
                    if tc_delta.function and tc_delta.function.arguments:
                        collected_tool_calls[idx]["arguments"] += tc_delta.function.arguments
                    if tc_delta.id:
                        collected_tool_calls[idx]["id"] = tc_delta.id
                    if tc_delta.function and tc_delta.function.name:
                        collected_tool_calls[idx]["name"] = tc_delta.function.name

    print(f"({chunk_count} chunks)")

    # Build message
    class _Msg:
        pass
    message = _Msg()
    message.content = "".join(collected_content) or None
    message.reasoning_content = "".join(reasoning_content_parts) if reasoning_content_parts else None
    if collected_tool_calls:
        class _TC:
            pass
        class _Fn:
            pass
        tcs = []
        for idx in sorted(collected_tool_calls):
            tc = _TC()
            tc.id = collected_tool_calls[idx]["id"]
            fn = _Fn()
            fn.name = collected_tool_calls[idx]["name"]
            fn.arguments = collected_tool_calls[idx]["arguments"]
            tc.function = fn
            tcs.append(tc)
        message.tool_calls = tcs
    else:
        message.tool_calls = None

    if usage_data:
        usage["input"] = getattr(usage_data, "prompt_tokens", 0) or 0
        usage["output"] = getattr(usage_data, "completion_tokens", 0) or 0

    # Extract thinking/reasoning content if present
    thinking_text = None
    # Some models (DeepSeek, Kimi) put reasoning in a separate field
    reasoning_content = getattr(message, "reasoning_content", None)
    if reasoning_content:
        thinking_text = reasoning_content
    # Some models wrap thinking in <think> tags in the content
    elif message.content and "<think>" in (message.content or ""):
        import re
        think_match = re.search(r"<think>(.*?)</think>", message.content, re.DOTALL)
        if think_match:
            thinking_text = think_match.group(1).strip()

    # Append assistant message to conversation
    if hasattr(message, "model_dump"):
        messages.append(message.model_dump(exclude_none=True))
    else:
        # Streaming path: build the message dict manually
        msg_dict = {"role": "assistant"}
        if message.content:
            msg_dict["content"] = message.content
        if message.tool_calls:
            msg_dict["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in message.tool_calls
            ]
        messages.append(msg_dict)

    # Handle proper tool calls
    if message.tool_calls:
        tool_calls = []
        for tc in message.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, TypeError):
                args = {}
            tool_calls.append({"id": tc.id, "name": tc.function.name, "input": args})
        return {"type": "tool_use", "tool_calls": tool_calls,
                "thinking": thinking_text, "usage": usage}

    text = message.content or ""
    # Strip <think> tags from visible text if we already captured them
    if thinking_text and "<think>" in text:
        import re
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # Fallback: some models dump tool calls as JSON in the text
    parsed_tc = _parse_json_tool_call(text)
    if parsed_tc:
        fake_id = f"fallback_{id(text)}"
        return {"type": "tool_use",
                "tool_calls": [{"id": fake_id, "name": parsed_tc["name"], "input": parsed_tc["input"]}],
                "thinking": None, "usage": usage}

    return {"type": "text", "text": text, "thinking": None, "usage": usage}


def _append_openai_tool_results(messages, tool_call_id, name, result):
    """Append a single tool result in OpenAI format."""
    messages.append({
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": result,
    })


# ---------------------------------------------------------------------------
# Main agent loop
# ---------------------------------------------------------------------------

def run_agent(
    game: str,
    model: str,
    max_turns: int,
    session_dir: str,
    thinking: bool = False,
    budget_tokens: int = 0,
    viewer=None,
    map_mode: str = "explore",
    backend: str = "fireworks",
) -> None:
    registry = ToolRegistry(map_mode=map_mode)
    system_prompt = _build_system_prompt(map_mode)
    logger = SessionLogger(session_dir, game=game, model=model)

    # Set up client and schemas based on backend
    if backend == "anthropic":
        import anthropic
        client = anthropic.Anthropic()
        tool_schemas = get_anthropic_schemas(map_mode)
    else:
        from openai import OpenAI
        if backend == "fireworks":
            api_key = os.environ.get("FIREWORKS_API_KEY")
            if not api_key:
                print("Error: FIREWORKS_API_KEY environment variable is not set.")
                print("Run: export FIREWORKS_API_KEY=your-key-here")
                sys.exit(1)
            client = OpenAI(
                api_key=api_key,
                base_url="https://api.fireworks.ai/inference/v1",
            )
        elif backend == "openai":
            client = OpenAI()
        else:
            raise ValueError(f"Unknown backend: {backend}")
        tool_schemas = get_openai_schemas(map_mode)

    is_anthropic = backend == "anthropic"

    print(f"Starting game: {game}")
    print(f"Backend: {backend} | Model: {model}")
    print(f"Thinking: {'on' if thinking else 'off'} | Map: {map_mode}")
    print(f"Session log: {logger.txt_path}")

    session = ZorkSession(game)
    opening_text = session.start()
    print(opening_text)
    print()

    opening_room = _detect_room(opening_text)
    if viewer and opening_room:
        viewer.set_room(opening_room)

    messages: list[dict] = [
        {"role": "user", "content": opening_text},
    ]

    total_input_tokens = 0
    total_output_tokens = 0

    for turn in range(1, max_turns + 1):
        tool_calls_this_turn: list[dict] = []
        thinking_text = None
        tool_rounds = 0
        max_tool_rounds = 10

        if viewer:
            viewer.log_event("turn_start", turn=turn)

        # Inner loop: handle tool use until we get a plain text response
        while True:
            if is_anthropic:
                result = _run_anthropic(
                    client, model, system_prompt, tool_schemas, messages,
                    thinking, budget_tokens,
                )
            else:
                result = _run_openai(
                    client, model, system_prompt, tool_schemas, messages,
                    thinking=thinking,
                )

            # Track tokens
            total_input_tokens += result["usage"]["input"]
            total_output_tokens += result["usage"]["output"]
            if viewer:
                viewer.set_tokens(total_input_tokens, total_output_tokens)

            if result.get("thinking"):
                thinking_text = result["thinking"]
                if viewer:
                    viewer.log_event("thinking", text=thinking_text)

            if result["type"] == "tool_use":
                for tc in result["tool_calls"]:
                    tool_result = registry.execute(tc["name"], tc["input"])
                    tool_calls_this_turn.append(
                        {"name": tc["name"], "input": tc["input"], "result": tool_result}
                    )
                    print(f"[{turn}] tool: {tc['name']}({tc['input']}) => {tool_result[:200]}")
                    if viewer:
                        viewer.log_event("tool_call", name=tc["name"], input=tc["input"], result=tool_result)

                    # Append tool result in the right format
                    if is_anthropic:
                        pass  # handled below
                    elif tc["id"].startswith("fallback_"):
                        # Model dumped JSON as text, send result as user message
                        messages.append({
                            "role": "user",
                            "content": f"Tool result for {tc['name']}: {tool_result}\n\nNow issue a game command. Your final line must be the command prefixed with \"> \".",
                        })
                    else:
                        _append_openai_tool_results(messages, tc["id"], tc["name"], tool_result)

                # For Anthropic, send all tool results at once
                if is_anthropic:
                    tool_results = []
                    for tc, tc_log in zip(result["tool_calls"], tool_calls_this_turn):
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tc["id"],
                            "content": tc_log["result"],
                        })
                    _append_anthropic_tool_results(messages, tool_results)

                tool_rounds += 1
                if tool_rounds >= max_tool_rounds:
                    # Force the model to stop calling tools and issue a command
                    messages.append({
                        "role": "user",
                        "content": "You have used too many tools this turn. Stop calling tools and issue a game command now. Your final line MUST be the command prefixed with \"> \".",
                    })
                continue

            # Got text response
            text = result["text"]
            break

        command = _extract_command(text)
        if command is None:
            # Give the model one more chance with a nudge
            messages.append({
                "role": "user",
                "content": "Now issue a game command. Your response must end with the command on its own line prefixed with \"> \".",
            })
            if is_anthropic:
                retry = _run_anthropic(client, model, system_prompt, tool_schemas, messages, thinking, budget_tokens)
            else:
                retry = _run_openai(client, model, system_prompt, tool_schemas, messages)
            total_input_tokens += retry["usage"]["input"]
            total_output_tokens += retry["usage"]["output"]
            if viewer:
                viewer.set_tokens(total_input_tokens, total_output_tokens)
            if retry["type"] == "text":
                text = retry["text"]
                command = _extract_command(text)

        if command is None:
            print(f"[turn {turn}] Could not parse a command from model response:")
            print(text)
            print("[Stopping]")
            break

        game_output = session.send_command(command)
        room = _detect_room(game_output)

        # Update viewer with streamed events
        if viewer:
            if room:
                viewer.set_room(room)
            # Send reasoning as thinking if we didn't already send thinking
            if not thinking_text and text.strip() != f"> {command}":
                reasoning_lines = [l for l in text.strip().split("\n") if not l.startswith(">")]
                if reasoning_lines:
                    viewer.log_event("thinking", text="\n".join(reasoning_lines))
            viewer.log_event("command", command=command, output=game_output, room=room)

        logger.log_turn(
            turn=turn,
            command=command,
            output=game_output,
            tool_calls=tool_calls_this_turn,
            thinking=thinking_text,
            reasoning=text,
            room=room,
        )

        # Terminal output
        if thinking_text:
            preview = thinking_text[:200]
            if len(thinking_text) > 200:
                preview += f"... ({len(thinking_text)} chars)"
            print(f"[{turn}] thinking: {preview}")
        if text.strip() != f"> {command}":
            reasoning_lines = [l for l in text.strip().split("\n") if not l.startswith(">")]
            if reasoning_lines:
                print(f"[{turn}] reasoning: {' '.join(reasoning_lines)[:200]}")
        print(f"[{turn}] > {command}")
        if room:
            print(f"[{turn}] room: {room}")
        print(game_output)
        print()

        messages.append({"role": "user", "content": game_output})

    session.close()
    logger.finalize(recorded_rooms=registry.recorded_rooms)
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
        "--backend",
        choices=["anthropic", "fireworks", "openai"],
        default="fireworks",
        help="API backend (default: fireworks)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model ID. Defaults depend on backend.",
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
        help="Enable extended thinking (Anthropic only).",
    )
    parser.add_argument(
        "--budget-tokens",
        type=int,
        default=0,
        help="Thinking budget tokens (Anthropic only). Implies --thinking.",
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
        help="Map mode: none, explore (default), full.",
    )
    args = parser.parse_args()

    # Default models per backend
    if args.model is None:
        defaults = {
            "fireworks": "accounts/fireworks/models/llama4-maverick-instruct-basic",
            "anthropic": "claude-sonnet-4-6",
            "openai": "gpt-4o",
        }
        args.model = defaults[args.backend]

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
                backend=args.backend,
            )
        except KeyboardInterrupt:
            pass
        finally:
            if viewer:
                viewer.close()

    if viewer:
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
