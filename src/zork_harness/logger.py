"""SessionLogger: writes a JSONL machine log and a human-readable transcript."""

import json
from datetime import datetime, timezone
from pathlib import Path


class SessionLogger:
    def __init__(self, session_dir: str | Path) -> None:
        session_dir = Path(session_dir)
        session_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self._jsonl_path = session_dir / f"session_{timestamp}.jsonl"
        self._txt_path = session_dir / f"session_{timestamp}.txt"

        self._jsonl = open(self._jsonl_path, "w", encoding="utf-8")
        self._txt = open(self._txt_path, "w", encoding="utf-8")

        self._txt.write(f"Zork Harness Session - {timestamp}\n")
        self._txt.write("=" * 60 + "\n\n")
        self._txt.flush()

    def log_turn(
        self,
        turn: int,
        command: str,
        output: str,
        tool_calls: list[dict] | None = None,
    ) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()

        record = {
            "turn": turn,
            "command": command,
            "output": output,
            "tool_calls": tool_calls or [],
            "timestamp": timestamp,
        }
        self._jsonl.write(json.dumps(record) + "\n")
        self._jsonl.flush()

        self._txt.write(f"--- Turn {turn} ---\n")
        if tool_calls:
            for tc in tool_calls:
                self._txt.write(f"[tool] {tc.get('name')}({tc.get('input', {})})\n")
                self._txt.write(f"       => {tc.get('result', '')}\n")
        self._txt.write(f"> {command}\n")
        self._txt.write(output + "\n\n")
        self._txt.flush()

    def close(self) -> None:
        self._jsonl.close()
        self._txt.close()

    @property
    def jsonl_path(self) -> Path:
        return self._jsonl_path

    @property
    def txt_path(self) -> Path:
        return self._txt_path
