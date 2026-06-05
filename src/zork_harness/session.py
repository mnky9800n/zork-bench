"""Game session: drives an interpreter inside Docker over the RemGlk JSON protocol.

The interpreter is bocfel (a Z-machine VM) compiled against remglk (a Glk I/O layer
that speaks structured JSON instead of drawing to a terminal). Each turn the harness
sends a JSON input event on stdin and reads a JSON "update" object from stdout, rather
than screen-scraping an ANSI terminal. This makes I/O robust (no prompt-guessing, no
escape-code stripping) and the status line (room + score) arrives as structured data.

RemGlk protocol used here (eblong.com/zarf/glk/remglk/docs.html):
  - First message:  {"type":"init","gen":0,"metrics":{"width":80,"height":24}}
  - Line input:     {"type":"line","gen":G,"window":W,"value":"go east"}
  - Char input:     {"type":"char","gen":G,"window":W,"value":"return"}
  - Update output:  {"type":"update","gen":N,"windows":[...],"content":[...],"input":[...]}
      * content entries with "text"  are buffer windows (the main prose)
      * content entries with "lines" are grid windows  (the status line)
      * the "input" array says which window wants input next, and the gen to echo back
"""

import json
import shutil
import subprocess
from abc import ABC, abstractmethod

from zork_harness.logger import SessionLogger


class GameSessionError(Exception):
    """Raised when the underlying game process becomes unusable.

    The agent loop catches this and terminates the session cleanly with a
    `termination_reason="game_session_error"` summary entry. The exception is
    deliberately interpreter-agnostic: RemGlkSession raises it on EOF or a dead
    process, but any future interpreter implementation (e.g. a Rust Z-machine VM)
    can raise the same type from its own dead-process detection without the agent
    loop needing to change.
    """


GAMES: dict[str, str] = {
    "abyss": "abyss-r1-s890320.z6",
    "amfv": "amfv-r77-s850814.z4",
    "arthur": "arthur-r74-s890714.z6",
    "ballyhoo": "ballyhoo-r97-s851218.z3",
    "beyondzork": "beyondzork-r57-s871221.z5",
    "borderzone": "borderzone-r9-s871008.z5",
    "bureaucracy": "bureaucracy-r116-s870602.z4",
    "cutthroats": "cutthroats-r23-s840809.z3",
    "deadline": "deadline-r27-s831005.z3",
    "enchanter": "enchanter-r29-s860820.z3",
    "hitchhiker": "hitchhiker-r60-s861002.z3",
    "hollywoodhijinx": "hollywoodhijinx-r37-s861215.z3",
    "infidel": "infidel-r22-s830916.z3",
    "journey": "journey-r83-s890706.z6",
    "leathergoddesses": "leathergoddesses-r59-s860730.z3",
    "lurkinghorror": "lurkinghorror-r203-s870506.z3",
    "minizork2": "minizork2-r2-s871123.z3",
    "minizork": "minizork-r34-s871124.z3",
    "moonmist": "moonmist-r9-s861022.z3",
    "nordandbert": "nordandbert-r19-s870722.z4",
    "planetfall": "planetfall-r37-s851003.z3",
    "plunderedhearts": "plunderedhearts-r26-s870730.z3",
    "restaurant": "restaurant-r184-s890412.z6",
    "seastalker": "seastalker-r18-s850919.z3",
    "sherlock-nosound": "sherlock-nosound-r4-s880324.z5",
    "sherlock": "sherlock-r26-s880127.z5",
    "shogun": "shogun-r322-s890706.z6",
    "sorcerer": "sorcerer-r15-s851108.z3",
    "spellbreaker": "spellbreaker-r87-s860904.z3",
    "starcross": "starcross-r17-s821021.z3",
    "stationfall": "stationfall-r107-s870430.z3",
    "suspect": "suspect-i190-r18-s850222.z3",
    "suspended": "suspended-mac-r8-s840521.z3",
    "trinity": "trinity-r12-s860926.z4",
    "wishbringer": "wishbringer-r69-s850920.z3",
    "witness": "witness-r22-s840924.z3",
    "zork0": "zork0-r393-s890714.z6",
    "zork1": "zork1-r88-s840726.z3",
    "zork2": "zork2-r48-s840904.z3",
    "zork3": "zork3-r17-s840727.z3",
}

# Path to the Dockerfile is at the project root, two levels above this file:
# src/zork_harness/session.py -> src/zork_harness -> src -> project root
_PROJECT_ROOT = str(__import__("pathlib").Path(__file__).parent.parent.parent)


def _ensure_docker_ready(image_name: str) -> None:
    """Ensure Docker is running and the game image is built.

    Steps:
    1. Check if Docker daemon is reachable via `docker info`.
    2. If not, and Colima is installed, start Colima automatically.
    3. Check whether the target image exists locally.
    4. If not, build it from the Dockerfile at the project root.
    """
    # Step 1: check if Docker is already reachable.
    result = subprocess.run(
        ["docker", "info"],
        capture_output=True,
    )
    docker_available = result.returncode == 0

    # Step 2: if Docker isn't reachable and Colima is installed, start it.
    if not docker_available:
        if shutil.which("colima") is None:
            raise RuntimeError(
                "Docker daemon is not running and Colima is not installed. "
                "Start Docker or install Colima before running zork-harness."
            )
        print("Docker not running. Starting Colima...")
        subprocess.run(["colima", "start"], check=True)
        print("Colima started.")

    # Step 3: check whether the image exists.
    result = subprocess.run(
        ["docker", "images", "-q", image_name],
        capture_output=True,
        text=True,
    )
    image_exists = bool(result.stdout.strip())

    # Step 4: build the image if it is missing.
    if not image_exists:
        print(f"Image '{image_name}' not found. Building from {_PROJECT_ROOT}/Dockerfile...")
        subprocess.run(
            ["docker", "build", "-t", image_name, _PROJECT_ROOT],
            check=True,
        )
        print(f"Image '{image_name}' built successfully.")


# ---------------------------------------------------------------------------
# RemGlk update parsing (pure functions, unit-tested without Docker)
# ---------------------------------------------------------------------------

def _decode_json_object(read_char) -> dict:
    """Read one complete JSON object from a stream, one character at a time.

    `read_char` is a zero-arg callable returning a single character (or "" at EOF).
    RemGlk emits one JSON object per update and then blocks waiting for input, so a
    pipe never signals "message done". We accumulate characters and attempt
    `raw_decode` until a complete object parses, which frames updates reliably even
    when an object spans multiple reads. Raises EOFError if the stream ends before a
    complete object is read.
    """
    decoder = json.JSONDecoder()
    buf = ""
    while True:
        ch = read_char()
        if ch == "":
            raise EOFError("stream closed before a complete JSON object was read")
        buf += ch
        stripped = buf.lstrip()
        if not stripped:
            continue
        try:
            obj, _ = decoder.raw_decode(stripped)
            return obj
        except json.JSONDecodeError:
            continue


def _extract_buffer_text(update: dict) -> str:
    """Concatenate the prose from all buffer windows in a RemGlk update.

    Buffer content entries carry a "text" array of paragraphs; grid (status-line)
    entries carry "lines" and are skipped here. The player's echoed command comes
    back as a run styled "input" and is dropped, and the trailing ">" prompt
    paragraph the game prints is stripped, so the result matches the prose the LLM
    would have read from the old terminal transport.
    """
    lines: list[str] = []
    for entry in update.get("content", []):
        if "text" not in entry:
            continue
        for para in entry["text"]:
            runs = para.get("content", [])
            line = "".join(
                run.get("text", "")
                for run in runs
                if run.get("style") != "input"
            )
            lines.append(line)

    # Drop trailing prompt markers and blank lines.
    while lines and lines[-1].strip() in (">", ""):
        lines.pop()
    # Drop leading blank lines (e.g. left by the filtered command echo).
    while lines and lines[0].strip() == "":
        lines.pop(0)

    return "\n".join(lines).strip()


def _extract_status_line(update: dict) -> str:
    """Concatenate the text of all grid (status-line) windows in a RemGlk update.

    For Z-machine games this is the bar showing the room name on the left and
    "Score: N  Moves: M" on the right.
    """
    parts: list[str] = []
    for entry in update.get("content", []):
        if "lines" not in entry:
            continue
        for line in entry["lines"]:
            runs = line.get("content", [])
            text = "".join(run.get("text", "") for run in runs)
            if text.strip():
                parts.append(text.strip())
    return "  ".join(parts)


def _select_input_request(update: dict) -> dict | None:
    """Return the input request to respond to next, preferring line over char."""
    requests = update.get("input", [])
    line_req = next((r for r in requests if r.get("type") == "line"), None)
    return line_req or (requests[0] if requests else None)


# ---------------------------------------------------------------------------
# Session interface and RemGlk implementation
# ---------------------------------------------------------------------------

class GameSession(ABC):
    """Interpreter-agnostic interface the agent loop drives.

    Implementations wrap a specific interpreter/transport but expose the same four
    methods, so a new VM can be dropped in without touching agent.py.
    """

    @abstractmethod
    def start(self) -> str:
        """Launch the game and return its opening text."""

    @abstractmethod
    def send_command(self, command: str) -> str:
        """Send a command and return the resulting game prose."""

    @abstractmethod
    def get_score(self) -> int | None:
        """Return the current score, or None if unknown."""

    @abstractmethod
    def close(self) -> None:
        """Terminate the game process."""


class RemGlkSession(GameSession):
    """Drives a bocfel+remglk interpreter in Docker over the RemGlk JSON protocol."""

    DOCKER_IMAGE = "zork-harness-game"
    # A char-input prompt (e.g. a death "press any key") is auto-advanced; this caps
    # how many consecutive char prompts we walk through before giving up.
    _MAX_CHAR_ADVANCE = 50

    def __init__(self, game_name: str = "zork1"):
        if game_name not in GAMES:
            raise ValueError(f"Unknown game '{game_name}'. Available: {sorted(GAMES)}")
        self.game_name = game_name
        self.game_file = GAMES[game_name]
        self.process: subprocess.Popen | None = None
        self._pending_input: dict | None = None
        self._status_line: str = ""

    def start(self) -> str:
        """Spawn the container, send the init handshake, and return the opening text."""
        _ensure_docker_ready(self.DOCKER_IMAGE)
        game_path = f"/home/frotz/DATA/{self.game_file}"
        self.process = subprocess.Popen(
            ["docker", "run", "--rm", "-i", self.DOCKER_IMAGE, game_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self._send({"type": "init", "gen": 0, "metrics": {"width": 80, "height": 24}})
        update = self._read_update()
        return self._consume_to_line_input(update)

    def send_command(self, command: str) -> str:
        """Send a command to the game and return the response prose.

        Raises GameSessionError if the game process is dead or dies during the read.
        """
        if self.process is None or self.process.poll() is not None:
            raise GameSessionError("Game session is not running.")
        if self._pending_input is None:
            raise GameSessionError("Game is not awaiting input.")

        self._send_input("line", command)
        update = self._read_update()
        return self._consume_to_line_input(update)

    def get_score(self) -> int | None:
        """Read the score from the cached status line (no command is sent to the game)."""
        if not self._status_line:
            return None
        return SessionLogger._parse_score(self._status_line)

    def close(self) -> None:
        """Terminate the game process."""
        if self.process and self.process.poll() is None:
            try:
                if self.process.stdin:
                    self.process.stdin.close()
            except OSError:
                pass
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None

    # -- internals ----------------------------------------------------------

    def _consume_to_line_input(self, update: dict) -> str:
        """Accumulate prose from `update`, auto-advancing through char-input prompts.

        Z-machine games occasionally request a keypress mid-response (a death "press
        any key", a "[MORE]" pause). We feed a return for each such char prompt and
        keep reading until the game asks for a line again, concatenating the prose so
        the caller sees one coherent response.
        """
        prose = [_extract_buffer_text(update)]
        self._capture_status(update)
        self._pending_input = _select_input_request(update)

        advances = 0
        while (
            self._pending_input is not None
            and self._pending_input.get("type") == "char"
            and advances < self._MAX_CHAR_ADVANCE
        ):
            self._send_input("char", "return")
            update = self._read_update()
            prose.append(_extract_buffer_text(update))
            self._capture_status(update)
            self._pending_input = _select_input_request(update)
            advances += 1

        text = "\n".join(part for part in prose if part).strip()
        return text or "[No response from game]"

    def _capture_status(self, update: dict) -> None:
        """Cache the latest non-empty status line for get_score()."""
        status = _extract_status_line(update)
        if status:
            self._status_line = status

    def _send_input(self, event_type: str, value: str) -> None:
        """Send a line or char input event to the window the game is awaiting."""
        req = self._pending_input
        if req is None:
            raise GameSessionError("Game is not awaiting input.")
        self._send({
            "type": event_type,
            "gen": req["gen"],
            "window": req["id"],
            "value": value,
        })

    def _send(self, obj: dict) -> None:
        if self.process is None or self.process.stdin is None:
            raise GameSessionError("Game session is not running.")
        try:
            self.process.stdin.write(json.dumps(obj) + "\n")
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise GameSessionError(f"Game process closed its input ({exc}).") from None

    def _read_update(self) -> dict:
        if self.process is None or self.process.stdout is None:
            raise GameSessionError("Game session is not running.")
        try:
            return _decode_json_object(lambda: self.process.stdout.read(1))
        except EOFError:
            raise GameSessionError("Game process ended unexpectedly (EOF).") from None
