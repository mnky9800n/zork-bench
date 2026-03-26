"""SessionLogger: writes a JSONL machine log, human-readable transcript, and session summary."""

import json
from datetime import datetime, timezone
from pathlib import Path


class SessionLogger:
    def __init__(self, session_dir: str | Path, game: str = "", model: str = "") -> None:
        session_dir = Path(session_dir)
        session_dir.mkdir(parents=True, exist_ok=True)

        self._timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self._jsonl_path = session_dir / f"session_{self._timestamp}.jsonl"
        self._txt_path = session_dir / f"session_{self._timestamp}.txt"

        self._jsonl = open(self._jsonl_path, "w", encoding="utf-8")
        self._txt = open(self._txt_path, "w", encoding="utf-8")

        self._game = game
        self._model = model

        # Room tracking
        self._rooms_visited: list[dict] = []  # {"turn": N, "room": str}
        self._unique_rooms: set[str] = set()
        self._last_turn = 0

        # Write header
        self._txt.write(f"Zork Harness Session - {self._timestamp}\n")
        self._txt.write(f"Game: {game} | Model: {model}\n")
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
    ) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        self._last_turn = turn

        # Track room visits
        if room:
            self._rooms_visited.append({"turn": turn, "room": room})
            self._unique_rooms.add(room)

        record = {
            "turn": turn,
            "command": command,
            "output": output,
            "tool_calls": tool_calls or [],
            "thinking": thinking,
            "reasoning": reasoning,
            "room": room,
            "timestamp": timestamp,
        }
        self._jsonl.write(json.dumps(record) + "\n")
        self._jsonl.flush()

        # Human-readable transcript
        self._txt.write(f"--- Turn {turn} ---\n")
        if thinking:
            # Include full thinking in transcript
            self._txt.write(f"[thinking]\n{thinking}\n[/thinking]\n\n")
        if reasoning:
            self._txt.write(f"[reasoning]\n{reasoning}\n[/reasoning]\n\n")
        if tool_calls:
            for tc in tool_calls:
                self._txt.write(f"[tool] {tc.get('name')}({tc.get('input', {})})\n")
                self._txt.write(f"       => {tc.get('result', '')}\n")
        if room:
            self._txt.write(f"[room] {room}\n")
        self._txt.write(f"> {command}\n")
        self._txt.write(output + "\n\n")
        self._txt.flush()

    def finalize(self) -> None:
        """Write session summary and close files."""
        # Write summary to transcript
        self._txt.write("=" * 60 + "\n")
        self._txt.write("SESSION SUMMARY\n")
        self._txt.write("=" * 60 + "\n")
        self._txt.write(f"Total turns: {self._last_turn}\n")
        self._txt.write(f"Unique rooms visited: {len(self._unique_rooms)}\n")
        if self._unique_rooms:
            self._txt.write("Rooms:\n")
            for room in sorted(self._unique_rooms):
                visits = [r["turn"] for r in self._rooms_visited if r["room"] == room]
                self._txt.write(f"  - {room} (turns: {', '.join(str(t) for t in visits)})\n")
        self._txt.write("\nRoom visit sequence:\n")
        for entry in self._rooms_visited:
            self._txt.write(f"  T{entry['turn']:03d}: {entry['room']}\n")
        self._txt.flush()

        # Write summary as final JSONL record
        summary = {
            "type": "summary",
            "game": self._game,
            "model": self._model,
            "total_turns": self._last_turn,
            "unique_rooms": len(self._unique_rooms),
            "rooms_list": sorted(self._unique_rooms),
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
