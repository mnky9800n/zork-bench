"""Live map viewer: split-pane window with zoomed map (left) and game log (right)."""

import queue
import threading
import tkinter as tk
from pathlib import Path

from PIL import Image, ImageTk

from zork_harness.map_coords import get_room_coords

MAP_IMAGE_PATH = Path(__file__).parent.parent.parent / "zork-1-map-ZUG-1982.jpeg"

POLL_INTERVAL_MS = 100
WINDOW_WIDTH = 1400
WINDOW_HEIGHT = 900
# How much of the pre-scaled map to show in the viewport
ZOOM_VIEWPORT = 900
# Pre-scale the full image to this width at startup for fast rendering
PRESCALE_WIDTH = 3200


class MapViewer:
    """Split-pane viewer: zoomed map on left, game log on right."""

    PLAYER_EMOJI = "\U0001F916"  # robot face

    def __init__(self, starting_room: str = "West of House") -> None:
        self._current_room: str | None = starting_room
        self._room_history: list[str] = [starting_room]
        self._turn_count = 0
        self._lock = threading.Lock()
        self._dirty = True
        self._input_tokens = 0
        self._output_tokens = 0
        self._cache_read = 0
        self._cache_create = 0
        self._root: tk.Tk | None = None
        self._map_canvas: tk.Canvas | None = None
        self._map_photo: ImageTk.PhotoImage | None = None
        self._map_image_id: int | None = None
        self._marker_items: list[int] = []
        self._trail_items: list[int] = []
        self._scaled_image: Image.Image | None = None
        self._prescale: float = 1.0  # ratio of prescaled to original
        self._log_widget: tk.Text | None = None
        self._pending_logs: list[dict] = []

        # Pan / follow state
        self._follow_player = True
        self._pan_center: tuple[int, int] | None = None
        self._drag_start: tuple[int, int] | None = None
        self._vp_x1 = 0
        self._vp_y1 = 0
        self._vp_x2 = 1
        self._vp_y2 = 1
        self._canvas_w = 1
        self._canvas_h = 1

    def set_tokens(self, input_tokens: int, output_tokens: int,
                   cache_read: int = 0, cache_create: int = 0) -> None:
        """Called from the agent thread to update token counts."""
        with self._lock:
            self._input_tokens = input_tokens
            self._output_tokens = output_tokens
            self._cache_read = cache_read
            self._cache_create = cache_create
            self._dirty = True

    def set_room(self, room_name: str) -> None:
        """Called from the agent thread to update the current room."""
        with self._lock:
            if room_name != self._current_room:
                self._current_room = room_name
                self._room_history.append(room_name)
                # Only snap back if follow mode is on
                if self._follow_player:
                    self._pan_center = None
                self._dirty = True

    def log_event(self, event_type: str, **data) -> None:
        """Stream a single event to the viewer log as it happens."""
        with self._lock:
            self._pending_logs.append({"_event": event_type, **data})

    def log(self, turn: int, command: str, output: str,
            thinking: str | None = None, reasoning: str | None = None,
            room: str | None = None, tool_calls: list[dict] | None = None) -> None:
        """Called from the agent thread to append the turn summary to the game log."""
        with self._lock:
            self._turn_count = turn
            self._dirty = True
            self._pending_logs.append({
                "turn": turn,
                "command": command,
                "output": output,
                "thinking": thinking,
                "reasoning": reasoning,
                "room": room,
                "tool_calls": tool_calls or [],
            })

    def _build_token_bar(self) -> None:
        """Build the token counter bar at the top of the window."""
        self._token_var = tk.StringVar(value="Tokens: 0 input | 0 output | 0 total")
        token_bar = tk.Label(
            self._root, textvariable=self._token_var,
            bg="#111111", fg="#00DDFF",
            font=("Menlo", 14, "bold"),
            anchor=tk.CENTER, pady=6,
        )
        token_bar.pack(side=tk.TOP, fill=tk.X)

    def _build_right_panel(self, right_frame: tk.Frame) -> None:
        """Build the log text widget and scrollbar inside right_frame."""
        log_label = tk.Label(
            right_frame, text="Game Log",
            bg="#000000", fg="#39FF14",
            font=("Menlo", 13, "bold"),
            anchor=tk.W, padx=8, pady=4,
        )
        log_label.pack(side=tk.TOP, fill=tk.X)

        self._log_widget = tk.Text(
            right_frame,
            bg="#0a0a0a", fg="#cccccc",
            font=("Menlo", 11),
            wrap=tk.WORD,
            state=tk.DISABLED,
            padx=8, pady=8,
            insertbackground="#39FF14",
            selectbackground="#333333",
            highlightthickness=0,
            borderwidth=0,
        )
        scrollbar = tk.Scrollbar(right_frame, command=self._log_widget.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._log_widget.configure(yscrollcommand=scrollbar.set)
        self._log_widget.pack(fill=tk.BOTH, expand=True)

        self._log_widget.tag_configure("turn", foreground="#39FF14", font=("Menlo", 11, "bold"))
        self._log_widget.tag_configure("command", foreground="#FFD700", font=("Menlo", 11, "bold"))
        self._log_widget.tag_configure("output", foreground="#cccccc")
        self._log_widget.tag_configure("thinking_header", foreground="#FF69B4", font=("Menlo", 11, "bold"))
        self._log_widget.tag_configure("thinking", foreground="#CC88CC", font=("Menlo", 10))
        self._log_widget.tag_configure("reasoning_header", foreground="#88aaff", font=("Menlo", 11, "bold"))
        self._log_widget.tag_configure("reasoning", foreground="#88aaff")
        self._log_widget.tag_configure("room", foreground="#39FF14")
        self._log_widget.tag_configure("tool_header", foreground="#FF8C00", font=("Menlo", 11, "bold"))
        self._log_widget.tag_configure("tool_call", foreground="#FFA500", font=("Menlo", 10))
        self._log_widget.tag_configure("tool_result", foreground="#DAA520", font=("Menlo", 10))

    def run(self) -> None:
        """Start the tkinter main loop. Must be called from the main thread."""
        self._root = tk.Tk()
        self._root.title("Zork Map - LLM Position Tracker")
        self._root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self._root.configure(bg="#1a1a1a")

        # Load and pre-scale the map for fast rendering
        original = Image.open(MAP_IMAGE_PATH)
        self._prescale = PRESCALE_WIDTH / original.width
        prescale_h = int(original.height * self._prescale)
        self._scaled_image = original.resize(
            (PRESCALE_WIDTH, prescale_h), Image.LANCZOS
        )
        original.close()

        # Top bar (token counter or title, depending on subclass)
        self._build_token_bar()

        # ── 50/50 split pane ──
        pane = tk.PanedWindow(
            self._root, orient=tk.HORIZONTAL,
            bg="#333333", sashwidth=4, sashrelief=tk.FLAT,
        )
        pane.pack(fill=tk.BOTH, expand=True)

        # ── Left panel: map ──
        left_frame = tk.Frame(pane, bg="#1a1a1a")

        # Status + follow toggle bar
        status_frame = tk.Frame(left_frame, bg="#000000")
        status_frame.pack(side=tk.TOP, fill=tk.X)

        self._status_var = tk.StringVar(value="Waiting for first move...")
        tk.Label(
            status_frame, textvariable=self._status_var,
            bg="#000000", fg="#39FF14",
            font=("Menlo", 13, "bold"),
            anchor=tk.W, padx=8, pady=4,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._follow_player = True
        self._follow_btn_var = tk.StringVar(value="Free Scroll")

        def toggle_follow():
            self._follow_player = not self._follow_player
            if self._follow_player:
                self._follow_btn_var.set("Free Scroll")
                self._pan_center = None
                self._dirty = True
            else:
                self._follow_btn_var.set("Follow Player")

        tk.Button(
            status_frame, textvariable=self._follow_btn_var,
            command=toggle_follow,
            font=("Menlo", 11), padx=8,
        ).pack(side=tk.RIGHT, padx=4, pady=2)

        self._map_canvas = tk.Canvas(
            left_frame, bg="#1a1a1a", highlightthickness=0,
            cursor="fleur",
        )
        self._map_canvas.pack(fill=tk.BOTH, expand=True)

        self._map_canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self._map_canvas.bind("<B1-Motion>", self._on_drag_motion)
        self._map_canvas.bind("<ButtonRelease-1>", self._on_drag_end)
        self._map_canvas.bind("<Double-Button-1>", self._on_snap_back)

        pane.add(left_frame, width=WINDOW_WIDTH // 2)

        # ── Right panel: log + optional input ──
        right_frame = tk.Frame(pane, bg="#1a1a1a")
        self._build_right_panel(right_frame)
        pane.add(right_frame, width=WINDOW_WIDTH // 2)

        self._render_map()
        self._root.after(POLL_INTERVAL_MS, self._poll)
        self._root.mainloop()

    # ── Mouse drag handlers ──

    def _on_drag_start(self, event) -> None:
        self._drag_start = (event.x, event.y)

    def _on_drag_motion(self, event) -> None:
        if self._drag_start is None:
            return
        dx_canvas = event.x - self._drag_start[0]
        dy_canvas = event.y - self._drag_start[1]
        self._drag_start = (event.x, event.y)

        scale_x = (self._vp_x2 - self._vp_x1) / max(self._canvas_w, 1)
        scale_y = (self._vp_y2 - self._vp_y1) / max(self._canvas_h, 1)

        if self._pan_center:
            cx, cy = self._pan_center
        else:
            cx = (self._vp_x1 + self._vp_x2) // 2
            cy = (self._vp_y1 + self._vp_y2) // 2

        img_w, img_h = self._scaled_image.size
        cx = max(0, min(img_w, cx + int(-dx_canvas * scale_x)))
        cy = max(0, min(img_h, cy + int(-dy_canvas * scale_y)))
        self._pan_center = (cx, cy)
        self._dirty = True

    def _on_drag_end(self, event) -> None:
        self._drag_start = None

    def _on_snap_back(self, event) -> None:
        """Double-click snaps back to following the LLM."""
        self._pan_center = None
        self._dirty = True

    # ── Polling and rendering ──

    def _poll(self) -> None:
        with self._lock:
            dirty = self._dirty
            pending = list(self._pending_logs)
            self._pending_logs.clear()

        # Append logs first (cheap), so text appears before the map re-renders
        if pending:
            self._append_logs(pending)
            dirty = True  # force map update to stay in sync with logs

        if dirty:
            self._render_map()
            with self._lock:
                self._dirty = False

        if self._root:
            self._root.after(POLL_INTERVAL_MS, self._poll)

    def _get_viewport_center(self, room, img_w, img_h):
        if self._pan_center:
            return self._pan_center
        if room:
            coords = get_room_coords(room)
            if coords:
                # Convert original-image coords to prescaled coords
                return (int(coords[0] * self._prescale),
                        int(coords[1] * self._prescale))
        # Default to West of House before the agent starts
        woh = get_room_coords("West of House")
        if woh:
            return (int(woh[0] * self._prescale), int(woh[1] * self._prescale))
        return (img_w // 2, img_h // 2)

    def _render_map(self) -> None:
        if not self._map_canvas or not self._scaled_image:
            return

        self._map_canvas.update_idletasks()
        canvas_w = self._map_canvas.winfo_width()
        canvas_h = self._map_canvas.winfo_height()
        if canvas_w < 10 or canvas_h < 10:
            return
        self._canvas_w = canvas_w
        self._canvas_h = canvas_h

        img_w, img_h = self._scaled_image.size

        with self._lock:
            room = self._current_room
            history = list(self._room_history)

        cx, cy = self._get_viewport_center(room, img_w, img_h)

        aspect = canvas_h / canvas_w
        vp_w = ZOOM_VIEWPORT
        vp_h = int(vp_w * aspect)

        x1 = max(0, cx - vp_w // 2)
        y1 = max(0, cy - vp_h // 2)
        x2 = x1 + vp_w
        y2 = y1 + vp_h
        if x2 > img_w:
            x2 = img_w
            x1 = max(0, x2 - vp_w)
        if y2 > img_h:
            y2 = img_h
            y1 = max(0, y2 - vp_h)

        self._vp_x1, self._vp_y1 = x1, y1
        self._vp_x2, self._vp_y2 = x2, y2

        cropped = self._scaled_image.crop((x1, y1, x2, y2))
        scaled = cropped.resize((canvas_w, canvas_h), Image.LANCZOS)
        self._map_photo = ImageTk.PhotoImage(scaled)

        # Clear old overlays
        for item in self._marker_items:
            self._map_canvas.delete(item)
        self._marker_items.clear()
        for item in self._trail_items:
            self._map_canvas.delete(item)
        self._trail_items.clear()

        if self._map_image_id is None:
            self._map_image_id = self._map_canvas.create_image(
                0, 0, anchor=tk.NW, image=self._map_photo
            )
        else:
            self._map_canvas.itemconfig(self._map_image_id, image=self._map_photo)

        sx = canvas_w / (x2 - x1)
        sy = canvas_h / (y2 - y1)
        ps = self._prescale

        def to_canvas(orig_x, orig_y):
            return (orig_x * ps - x1) * sx, (orig_y * ps - y1) * sy

        def in_view(px, py):
            return -50 <= px <= canvas_w + 50 and -50 <= py <= canvas_h + 50

        # Trail dots
        seen = set()
        for past_room in history[:-1]:
            if past_room in seen or past_room == room:
                continue
            seen.add(past_room)
            rc = get_room_coords(past_room)
            if rc:
                px, py = to_canvas(*rc)
                if in_view(px, py):
                    r = 5
                    self._trail_items.append(self._map_canvas.create_oval(
                        px - r, py - r, px + r, py + r,
                        fill="#4488FF", outline="#FFFFFF", width=1,
                    ))

        # Current position
        if room:
            rc = get_room_coords(room)
            if rc:
                px, py = to_canvas(*rc)
                if in_view(px, py):
                    for r, w in [(30, 4), (24, 3), (18, 2)]:
                        self._marker_items.append(self._map_canvas.create_oval(
                            px - r, py - r, px + r, py + r,
                            outline="#39FF14", width=w,
                        ))
                    self._marker_items.append(self._map_canvas.create_text(
                        px, py,
                        anchor=tk.CENTER,
                        text=self.PLAYER_EMOJI,
                        font=("Apple Color Emoji", 56),
                    ))

        # Update token counter (only present in the LLM viewer)
        if hasattr(self, "_token_var"):
            with self._lock:
                inp_tok = self._input_tokens
                out_tok = self._output_tokens
            total_tok = inp_tok + out_tok
            self._token_var.set(
                f"Tokens: {inp_tok:,} input  |  {out_tok:,} output  |  {total_tok:,} total"
            )

        # Status bar
        with self._lock:
            turns = self._turn_count
        unique = len(set(history))
        status = f"Room: {room or '???'}"
        if room and not get_room_coords(room):
            status += " (not on map)"
        status += f"  |  Rooms: {unique}  |  Turn: {turns}"
        if self._pan_center:
            status += "  |  [drag to pan, double-click to snap back]"
        self._status_var.set(status)

    @staticmethod
    def _format_tool_input(name: str, inp: dict) -> str:
        """Format tool input as human-readable text."""
        if name == "record_room":
            room = inp.get("room_name", "?")
            exits = inp.get("exits", {})
            items = inp.get("items", [])
            lines = [f'  Recording room: "{room}"']
            if exits:
                lines.append("  Exits:")
                for d, dest in exits.items():
                    lines.append(f"    {d} -> {dest}")
            if items:
                lines.append(f"  Items: {', '.join(items)}")
            return "\n".join(lines)
        elif name == "look_up_room":
            return f'  Looking up: "{inp.get("room_name", "?")}"'
        elif name == "list_known_rooms":
            return "  Listing all known rooms"
        elif name == "find_path":
            return f'  Finding path: {inp.get("from_room", "?")} -> {inp.get("to_room", "?")}'
        elif name == "update_inventory":
            action = inp.get("action", "?")
            item = inp.get("item", "?")
            verb = "Picked up" if action == "add" else "Dropped"
            return f"  {verb}: {item}"
        elif name == "add_note":
            return f'  Note: "{inp.get("note", "")}"'
        return f"  {inp}"

    @staticmethod
    def _format_tool_result(name: str, result: str) -> str:
        """Format tool result as human-readable text."""
        # Try to parse as a dict-like string for common cases
        if name == "record_room":
            return "  Saved to map."
        elif name == "find_path" and "No known path" in result:
            return f"  {result}"
        elif name == "find_path" and "path" in result:
            # Try to make the path steps readable
            try:
                import ast
                data = ast.literal_eval(result)
                if isinstance(data, dict) and "path" in data:
                    steps = data["path"]
                    if not steps:
                        return "  Already there!"
                    route = " -> ".join(
                        f'{s["direction"]} to {s["room"]}' for s in steps
                    )
                    return f"  Route: {route}"
            except (ValueError, SyntaxError, KeyError):
                pass
        elif name == "look_up_room":
            try:
                import ast
                data = ast.literal_eval(result)
                if isinstance(data, dict) and "exits" in data:
                    exits = data["exits"]
                    items = data.get("items", [])
                    parts = []
                    if exits:
                        exit_str = ", ".join(f"{d} -> {r}" for d, r in exits.items())
                        parts.append(f"  Exits: {exit_str}")
                    if items:
                        parts.append(f"  Items: {', '.join(items)}")
                    return "\n".join(parts) if parts else "  (empty room)"
            except (ValueError, SyntaxError, KeyError):
                pass
            if "not recorded yet" in result:
                return f"  {result}"
        elif name == "list_known_rooms":
            try:
                import ast
                data = ast.literal_eval(result)
                if isinstance(data, dict) and "count" in data:
                    return f"  {data['count']} rooms mapped"
            except (ValueError, SyntaxError, KeyError):
                pass
        elif name == "update_inventory":
            try:
                import ast
                items = ast.literal_eval(result)
                if isinstance(items, list):
                    if items:
                        return f"  Inventory: {', '.join(items)}"
                    return "  Inventory is empty"
            except (ValueError, SyntaxError):
                pass
        elif name == "add_note":
            return f"  {result}"
        # Fallback: truncate raw result
        if len(result) > 200:
            return f"  {result[:200]}..."
        return f"  {result}"

    @staticmethod
    def _format_game_output(text: str) -> str:
        """Re-flow game output for display.

        Frotz hard-wraps lines at ~80 columns. We join continuation lines
        back into paragraphs so the tk Text widget can re-wrap them naturally.
        Blank lines, indented lines (inventory lists), and short lines
        (room names, score) are kept as-is.
        """
        raw_lines = text.strip().split("\n")
        paragraphs: list[str] = []
        current: list[str] = []

        for line in raw_lines:
            stripped = line.rstrip()

            # Blank line: flush current paragraph, keep the blank
            if not stripped:
                if current:
                    paragraphs.append(" ".join(current))
                    current = []
                paragraphs.append("")
                continue

            # Indented lines (inventory, item lists) stay on their own
            if stripped.startswith("  ") or stripped.startswith("\t"):
                if current:
                    paragraphs.append(" ".join(current))
                    current = []
                paragraphs.append(stripped)
                continue

            # Short lines are likely room names, score, or standalone text
            if len(stripped) < 30:
                if current:
                    paragraphs.append(" ".join(current))
                    current = []
                paragraphs.append(stripped)
                continue

            # Otherwise it's a continuation of the current paragraph
            current.append(stripped)

        if current:
            paragraphs.append(" ".join(current))

        return "\n".join(paragraphs)

    def _append_logs(self, entries: list[dict]) -> None:
        if not self._log_widget:
            return

        self._log_widget.configure(state=tk.NORMAL)

        for entry in entries:
            # Handle streamed events (tool calls, thinking, etc.)
            event = entry.get("_event")
            if event == "turn_start":
                self._log_widget.insert(tk.END, f"--- Turn {entry.get('turn', '?')} ---\n", "turn")
                if entry.get("room"):
                    self._log_widget.insert(tk.END, f"  Location: {entry['room']}\n", "room")
                continue
            elif event == "thinking":
                self._log_widget.insert(tk.END, "Thinking:\n", "thinking_header")
                self._log_widget.insert(tk.END, entry.get("text", "") + "\n\n", "thinking")
                continue
            elif event == "tool_call":
                name = entry.get("name", "?")
                inp = entry.get("input", {})
                res = entry.get("result", "")
                display_name = name.replace("_", " ").title()
                self._log_widget.insert(tk.END, f"{display_name}:\n", "tool_header")
                self._log_widget.insert(
                    tk.END, self._format_tool_input(name, inp) + "\n", "tool_call",
                )
                self._log_widget.insert(
                    tk.END, self._format_tool_result(name, str(res)) + "\n\n", "tool_result",
                )
                continue
            elif event == "command":
                self._log_widget.insert(tk.END, f"  > {entry.get('command', '?')}\n\n", "command")
                game_text = self._format_game_output(entry.get("output", ""))
                self._log_widget.insert(tk.END, game_text + "\n\n\n", "output")
                continue
            elif event is not None:
                continue

            # Legacy: full turn entry (for backwards compat)
            turn = entry.get("turn", "?")
            self._log_widget.insert(tk.END, f"--- Turn {turn} ---\n", "turn")

            if entry.get("room"):
                self._log_widget.insert(tk.END, f"  Location: {entry['room']}\n", "room")

            if entry.get("thinking"):
                self._log_widget.insert(tk.END, "Thinking:\n", "thinking_header")
                self._log_widget.insert(tk.END, entry["thinking"] + "\n\n", "thinking")
            elif entry.get("reasoning"):
                lines = [l for l in entry["reasoning"].strip().split("\n") if not l.startswith(">")]
                if lines:
                    self._log_widget.insert(tk.END, "Thinking:\n", "thinking_header")
                    self._log_widget.insert(tk.END, "\n".join(lines) + "\n\n", "thinking")

            if entry.get("tool_calls"):
                for tc in entry["tool_calls"]:
                    name = tc.get("name", "?")
                    inp = tc.get("input", {})
                    res = tc.get("result", "")
                    display_name = name.replace("_", " ").title()
                    self._log_widget.insert(tk.END, f"{display_name}:\n", "tool_header")
                    self._log_widget.insert(
                        tk.END, self._format_tool_input(name, inp) + "\n", "tool_call",
                    )
                    self._log_widget.insert(
                        tk.END, self._format_tool_result(name, str(res)) + "\n\n", "tool_result",
                    )

            # Command
            self._log_widget.insert(tk.END, f"  > {entry['command']}\n\n", "command")

            # Game output, cleaned up
            game_text = self._format_game_output(entry["output"])
            self._log_widget.insert(tk.END, game_text + "\n\n", "output")

            # Separator
            self._log_widget.insert(tk.END, "\n")

        self._log_widget.configure(state=tk.DISABLED)
        self._log_widget.see(tk.END)

    def close(self) -> None:
        if self._root:
            self._root.quit()


class HumanMapViewer(MapViewer):
    """MapViewer subclass for human play: adds a command input field."""

    PLAYER_EMOJI = "\U0001F467"  # girl emoji

    def __init__(self, starting_room: str = "West of House") -> None:
        super().__init__(starting_room)
        self._command_queue: queue.Queue[str] = queue.Queue()
        self.closed = threading.Event()

    def get_command(self, timeout: float = 0.5) -> str | None:
        """Block up to timeout seconds for a command typed by the human.

        Returns the command string, or None if the timeout elapsed with no input.
        """
        try:
            return self._command_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def _build_token_bar(self) -> None:
        """Replace the token counter with a simple title bar."""
        title_bar = tk.Label(
            self._root, text="Zork - Human Player",
            bg="#111111", fg="#00DDFF",
            font=("Menlo", 14, "bold"),
            anchor=tk.CENTER, pady=6,
        )
        title_bar.pack(side=tk.TOP, fill=tk.X)

    def _build_right_panel(self, right_frame: tk.Frame) -> None:
        """Build the log widget plus a command input field at the bottom."""
        super()._build_right_panel(right_frame)

        # Input row: "> " label + entry field
        input_frame = tk.Frame(right_frame, bg="#0a0a0a")
        input_frame.pack(side=tk.BOTTOM, fill=tk.X)

        prompt_label = tk.Label(
            input_frame, text="> ",
            bg="#0a0a0a", fg="#39FF14",
            font=("Menlo", 13, "bold"),
            padx=4, pady=6,
        )
        prompt_label.pack(side=tk.LEFT)

        self._entry_var = tk.StringVar()
        self._entry = tk.Entry(
            input_frame,
            textvariable=self._entry_var,
            bg="#0a0a0a", fg="#39FF14",
            font=("Menlo", 13),
            insertbackground="#39FF14",
            highlightthickness=1,
            highlightcolor="#39FF14",
            highlightbackground="#222222",
            relief=tk.FLAT,
        )
        self._entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self._entry.bind("<Return>", self._on_submit)

    def _on_submit(self, _event=None) -> None:
        """Called when the user presses Enter in the input field."""
        command = self._entry_var.get().strip()
        if command:
            self._command_queue.put(command)
            self._entry_var.set("")

    def run(self) -> None:
        """Start the viewer; grabs input focus after the window opens."""
        super().run()

    def _render_map(self) -> None:
        """Render the map and grab entry focus on the first call."""
        super()._render_map()
        # Give the entry focus once the window is visible
        if hasattr(self, "_entry") and self._entry:
            self._entry.focus_set()

    def close(self) -> None:
        self.closed.set()
        super().close()
