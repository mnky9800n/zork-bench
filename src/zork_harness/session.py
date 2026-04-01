"""ZorkSession: spawns the game container via docker and communicates over stdin/stdout."""

import re
import shutil
import subprocess
import pexpect

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

_ANSI_ESCAPE = re.compile(r"\x1b\[[^a-zA-Z]*[a-zA-Z]")

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


class ZorkSession:
    """Manages a dfrotz process running inside a Docker container."""

    DOCKER_IMAGE = "zork-harness-game"

    def __init__(self, game_name: str = "zork1"):
        if game_name not in GAMES:
            raise ValueError(f"Unknown game '{game_name}'. Available: {sorted(GAMES)}")
        self.game_name = game_name
        self.game_file = GAMES[game_name]
        self.process: pexpect.spawn | None = None

    def start(self) -> str:
        """Spawn the Docker container and return the game's opening text."""
        _ensure_docker_ready(self.DOCKER_IMAGE)
        game_path = f"/home/frotz/DATA/{self.game_file}"
        cmd = f"docker run --rm -i {self.DOCKER_IMAGE} {game_path}"
        self.process = pexpect.spawn(
            cmd,
            encoding="utf-8",
            timeout=15,
        )
        # Docker cold start can take a while, use a longer timeout
        return self._read_until_prompt(timeout=30)

    def send_command(self, command: str) -> str:
        """Send a command to the game and return the response text."""
        if self.process is None or not self.process.isalive():
            raise RuntimeError("Game session is not running. Call start() first.")

        self.process.sendline(command)
        response = self._read_until_prompt()

        # Strip the echoed command that dfrotz reflects back
        lines = response.split("\n")
        if lines and command.lower() in lines[0].lower():
            response = "\n".join(lines[1:]).strip()

        return response if response else "[No response from game]"

    def close(self) -> None:
        """Terminate the game process."""
        if self.process and self.process.isalive():
            self.process.terminate(force=True)
        self.process = None

    def _read_until_prompt(self, timeout: int = 10) -> str:
        """Read output until dfrotz is waiting for input (prompt ends with '>\\n')."""
        try:
            self.process.expect(r"\n>", timeout=timeout)
            output = self.process.before
        except pexpect.TIMEOUT:
            output = self.process.before or ""
        except pexpect.EOF:
            return "[Game process ended]"

        return _ANSI_ESCAPE.sub("", output).strip()
