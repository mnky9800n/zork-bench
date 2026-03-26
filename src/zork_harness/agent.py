"""LLM agent loop: plays Zork by driving a ZorkSession through the Anthropic API."""

import argparse
import re
import sys

import anthropic

from zork_harness.logger import SessionLogger
from zork_harness.session import GAMES, ZorkSession
from zork_harness.tools import TOOL_SCHEMAS, ToolRegistry

SYSTEM_PROMPT = """\
You are playing Zork, a classic text adventure game. Your goal is to explore the world, \
collect treasures, solve puzzles, and maximize your score.

Rules:
- Use short, imperative commands: "go north", "take lamp", "open mailbox", "look", "inventory".
- Do not use elaborate sentences. The game parser only understands simple commands.
- You have tools available: look_up_map (check known room data), update_inventory \
(track items you pick up or drop), add_note (record observations for yourself).
- Think briefly, then issue exactly ONE game command per turn.
- Your final line MUST be the command on its own line, prefixed with "> ".

Example turn:
I should explore west. The living room likely has useful items.
> go west
"""

_COMMAND_RE = re.compile(r"^>\s*(.+)$", re.MULTILINE)


def _extract_command(text: str) -> str | None:
    """Extract the last "> command" line from the model's text response."""
    matches = _COMMAND_RE.findall(text)
    if not matches:
        return None
    return matches[-1].strip()


def run_agent(
    game: str,
    model: str,
    max_turns: int,
    session_dir: str,
    budget_tokens: int = 0,
) -> None:
    client = anthropic.Anthropic()
    registry = ToolRegistry()
    logger = SessionLogger(session_dir)

    print(f"Starting game: {game}")
    print(f"Session log: {logger.txt_path}")

    session = ZorkSession(game)
    opening_text = session.start()
    print(opening_text)
    print()

    # The conversation history sent to the API each turn
    messages: list[dict] = [
        {"role": "user", "content": opening_text},
    ]

    for turn in range(1, max_turns + 1):
        tool_calls_this_turn: list[dict] = []

        # Inner loop: handle tool use until we get a plain text response
        while True:
            api_kwargs = dict(
                model=model,
                max_tokens=budget_tokens + 4096 if budget_tokens else 1024,
                system=SYSTEM_PROMPT,
                tools=TOOL_SCHEMAS,
                messages=messages,
            )
            if budget_tokens:
                api_kwargs["thinking"] = {
                    "type": "adaptive",
                    "budget_tokens": budget_tokens,
                }
            # Use streaming to avoid timeout on long thinking requests
            response = client.messages.create(**api_kwargs, stream=True)
            response = response.get_final_message()

            # Append the assistant's response to the conversation
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    result = registry.execute(block.name, block.input)
                    tool_calls_this_turn.append(
                        {"name": block.name, "input": block.input, "result": result}
                    )
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
        logger.log_turn(turn, command, game_output, tool_calls_this_turn)

        print(f"[{turn}] > {command}")
        print(game_output)
        print()

        # Feed the game response back as the next user message
        messages.append({"role": "user", "content": game_output})

    session.close()
    logger.close()
    print(f"Session ended. Transcript: {logger.txt_path}")


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
        "--budget-tokens",
        type=int,
        default=0,
        help="Thinking budget tokens. 0 disables extended thinking (default: 0).",
    )
    args = parser.parse_args()

    try:
        run_agent(
            game=args.game,
            model=args.model,
            max_turns=args.max_turns,
            session_dir=args.session_dir,
            budget_tokens=args.budget_tokens,
        )
    except KeyboardInterrupt:
        print("\n[Interrupted]")
        sys.exit(0)


if __name__ == "__main__":
    main()
