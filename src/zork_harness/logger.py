"""SessionLogger: writes a JSONL machine log, human-readable transcript, and session summary."""

import json
from datetime import datetime, timezone
from pathlib import Path


class SessionLogger:
    def __init__(
        self,
        session_dir: str | Path,
        game: str = "",
        model: str = "",
        backend: str = "",
        map_mode: str = "",
    ) -> None:
        session_dir = Path(session_dir)
        session_dir.mkdir(parents=True, exist_ok=True)

        self._timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self._jsonl_path = session_dir / f"session_{self._timestamp}.jsonl"
        self._txt_path = session_dir / f"session_{self._timestamp}.txt"

        self._jsonl = open(self._jsonl_path, "w", encoding="utf-8")
        self._txt = open(self._txt_path, "w", encoding="utf-8")

        self._game = game
        self._model = model
        self._backend = backend
        self._map_mode = map_mode

        # Tracking
        self._rooms_visited: list[dict] = []
        self._unique_rooms: set[str] = set()
        self._deaths: list[int] = []
        self._last_turn = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0

        # Write JSONL header record
        header = {
            "type": "header",
            "game": game,
            "model": model,
            "backend": backend,
            "map_mode": map_mode,
            "player_type": "human" if backend == "human" else "llm",
            "started_at": self._timestamp,
        }
        self._jsonl.write(json.dumps(header) + "\n")
        self._jsonl.flush()

        # Write transcript header
        player = "Human" if backend == "human" else f"{model} ({backend})"
        self._txt.write(f"Zork Harness Session - {self._timestamp}\n")
        self._txt.write(f"Game: {game} | Player: {player}\n")
        if map_mode:
            self._txt.write(f"Map mode: {map_mode}\n")
        self._txt.write("=" * 60 + "\n\n")
        self._txt.flush()

    def log_turn(
        self,
        turn: int,
        command: str,
        output: str,
        tool_calls: list[dict] | None = None,
        thinking: str | None = None,
        reasoning: str | None = None,
        room: str | None = None,
        score: int | None = None,
    ) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        self._last_turn = turn

        # Track room visits
        if room:
            self._rooms_visited.append({"turn": turn, "room": room})
            self._unique_rooms.add(room)

        # Detect deaths
        died = "you have died" in output.lower()
        if died:
            self._deaths.append(turn)

        # Use explicitly provided score, or try to parse from output
        if score is None:
            score = self._parse_score(output)

        record = {
            "type": "turn",
            "turn": turn,
            "command": command,
            "output": output,
            "tool_calls": tool_calls or [],
            "thinking": thinking,
            "reasoning": reasoning,
            "room": room,
            "died": died,
            "score": score,
            "timestamp": timestamp,
        }
        self._jsonl.write(json.dumps(record) + "\n")
        self._jsonl.flush()

        # Human-readable transcript
        self._txt.write(f"--- Turn {turn} ---\n")
        if thinking:
            self._txt.write(f"[thinking]\n{thinking}\n[/thinking]\n\n")
        if reasoning:
            self._txt.write(f"[reasoning]\n{reasoning}\n[/reasoning]\n\n")
        if tool_calls:
            for tc in tool_calls:
                self._txt.write(f"[tool] {tc.get('name')}({tc.get('input', {})})\n")
                self._txt.write(f"       => {tc.get('result', '')}\n")
        if room:
            self._txt.write(f"[room] {room}\n")
        if died:
            self._txt.write("[DIED]\n")
        if score is not None:
            self._txt.write(f"[score] {score}\n")
        self._txt.write(f"> {command}\n")
        self._txt.write(output + "\n\n")
        self._txt.flush()

    def set_tokens(self, input_tokens: int, output_tokens: int) -> None:
        """Update cumulative token counts (LLM sessions only)."""
        self._total_input_tokens = input_tokens
        self._total_output_tokens = output_tokens

    def finalize(self, recorded_rooms: set[str] | None = None) -> None:
        """Write session summary and close files."""
        phantom_rooms: set[str] = set()
        if recorded_rooms:
            phantom_rooms = recorded_rooms - self._unique_rooms

        # Text summary
        self._txt.write("=" * 60 + "\n")
        self._txt.write("SESSION SUMMARY\n")
        self._txt.write("=" * 60 + "\n")
        self._txt.write(f"Player: {self._model} ({self._backend})\n")
        self._txt.write(f"Total turns: {self._last_turn}\n")
        self._txt.write(f"Deaths: {len(self._deaths)}\n")
        if self._deaths:
            self._txt.write(f"  Turns: {', '.join(str(t) for t in self._deaths)}\n")
        self._txt.write(f"Unique rooms visited: {len(self._unique_rooms)}\n")
        if self._unique_rooms:
            self._txt.write("Rooms:\n")
            for room in sorted(self._unique_rooms):
                visits = [r["turn"] for r in self._rooms_visited if r["room"] == room]
                self._txt.write(f"  - {room} (turns: {', '.join(str(t) for t in visits)})\n")
        if self._total_input_tokens:
            total = self._total_input_tokens + self._total_output_tokens
            self._txt.write(f"\nTokens: {self._total_input_tokens:,} input, "
                            f"{self._total_output_tokens:,} output, {total:,} total\n")
        if recorded_rooms:
            self._txt.write(f"\nRooms recorded by model: {len(recorded_rooms)}\n")
        if phantom_rooms:
            self._txt.write(f"Phantom rooms (recorded but never visited): {len(phantom_rooms)}\n")
            for room in sorted(phantom_rooms):
                self._txt.write(f"  - {room}\n")
        self._txt.write("\nRoom visit sequence:\n")
        for entry in self._rooms_visited:
            self._txt.write(f"  T{entry['turn']:03d}: {entry['room']}\n")
        self._txt.flush()

        # JSONL summary record
        summary = {
            "type": "summary",
            "game": self._game,
            "model": self._model,
            "backend": self._backend,
            "map_mode": self._map_mode,
            "player_type": "human" if self._backend == "human" else "llm",
            "total_turns": self._last_turn,
            "deaths": len(self._deaths),
            "death_turns": self._deaths,
            "unique_rooms": len(self._unique_rooms),
            "rooms_list": sorted(self._unique_rooms),
            "rooms_recorded_by_model": len(recorded_rooms) if recorded_rooms else 0,
            "phantom_rooms": sorted(phantom_rooms),
            "phantom_room_count": len(phantom_rooms),
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "room_sequence": self._rooms_visited,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._jsonl.write(json.dumps(summary) + "\n")
        self._jsonl.flush()

        self._jsonl.close()
        self._txt.close()

    def close(self) -> None:
        """Close without summary (for crash safety)."""
        self._jsonl.close()
        self._txt.close()

    @property
    def jsonl_path(self) -> Path:
        return self._jsonl_path

    @property
    def txt_path(self) -> Path:
        return self._txt_path

    @staticmethod
    def _parse_score(output: str) -> int | None:
        """Try to extract a score from game output."""
        import re
        # "Your score is 25 (total of 350 points)"
        m = re.search(r"your score is (\d+)", output.lower())
        if m:
            return int(m.group(1))
        # "Score: 25"
        m = re.search(r"score[:\s]+(\d+)", output.lower())
        if m:
            return int(m.group(1))
        return None
