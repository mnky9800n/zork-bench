"""Human play mode: drives a ZorkSession from keyboard input via the HumanMapViewer."""

from zork_harness.agent import RoomTracker
from zork_harness.logger import SessionLogger
from zork_harness.session import ZorkSession


def run_human_session(game: str, viewer, session_dir: str) -> None:
    """Run a human-controlled Zork session.

    Reads commands from viewer.get_command(), sends them to the game,
    displays output in the viewer, and logs everything to session_dir.
    """
    logger = SessionLogger(session_dir, game=game, model="human", backend="human")
    session = ZorkSession(game)
    room_tracker = RoomTracker()

    try:
        opening_text = session.start()
    except Exception as exc:
        viewer.log_event("command", command="[startup]", output=f"Failed to start game: {exc}")
        logger.finalize()
        viewer.close()
        return

    # Show opening text and detect starting room
    viewer.log_event("command", command="[game start]", output=opening_text)
    opening_room = room_tracker.detect_room(opening_text)
    if opening_room:
        viewer.set_room(opening_room)

    turn = 0

    try:
        while not viewer.closed.is_set():
            command = viewer.get_command(timeout=0.5)
            if command is None:
                continue

            turn += 1
            viewer.log_event("turn_start", turn=turn, room=viewer._current_room)

            try:
                game_output = session.send_command(command)
            except Exception as exc:
                game_output = f"[Error communicating with game: {exc}]"

            room = room_tracker.detect_room(game_output, last_command=command)
            if room:
                viewer.set_room(room)

            viewer.log_event("command", command=command, output=game_output, room=room)

            logger.log_turn(
                turn=turn,
                command=command,
                output=game_output,
                room=room,
            )
    finally:
        session.close()
        logger.finalize()
