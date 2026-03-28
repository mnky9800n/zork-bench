"""Interactive map calibration tool.

Opens the Zork map and prompts you to click on each room's location.
Scroll around the map, click to place a marker, then Confirm or click
again to reposition. Saves the coordinates to map_coords.py when done.

Usage:
    uv run python -m zork_harness.calibrate_map
"""

import tkinter as tk
from pathlib import Path

from PIL import Image, ImageTk

from zork_harness.map_coords import ROOM_COORDS

MAP_IMAGE_PATH = Path(__file__).parent.parent.parent / "zork-1-map-ZUG-1982.jpeg"
COORDS_FILE = Path(__file__).parent / "map_coords.py"

DISPLAY_WIDTH = 1600


def run_calibration():
    root = tk.Tk()
    root.title("Zork Map Calibration")

    original = Image.open(MAP_IMAGE_PATH)
    scale = DISPLAY_WIDTH / original.width
    display_height = int(original.height * scale)
    scaled = original.resize((DISPLAY_WIDTH, display_height), Image.LANCZOS)

    room_names = sorted(ROOM_COORDS.keys())
    current_index = [0]
    new_coords: dict[str, tuple[int, int]] = {}

    # Pending click (not yet confirmed)
    pending_click: list[tuple[int, int] | None] = [None]  # (full_x, full_y)
    pending_marker_items: list[int] = []
    old_marker_items: list[int] = []

    # ── Top bar ──
    top_frame = tk.Frame(root, bg="#000000")
    top_frame.pack(side=tk.TOP, fill=tk.X)

    prompt_var = tk.StringVar()
    tk.Label(
        top_frame, textvariable=prompt_var,
        bg="#000000", fg="#39FF14",
        font=("Menlo", 18, "bold"), pady=10,
    ).pack(side=tk.LEFT, padx=20)

    progress_var = tk.StringVar()
    tk.Label(
        top_frame, textvariable=progress_var,
        bg="#000000", fg="#AAAAAA",
        font=("Menlo", 14), pady=10,
    ).pack(side=tk.LEFT, padx=10)

    # ── Button bar ──
    btn_frame = tk.Frame(root, bg="#222222")
    btn_frame.pack(side=tk.TOP, fill=tk.X, pady=4)

    status_var = tk.StringVar(value="Scroll around, then click on the room's box center.")
    tk.Label(
        btn_frame, textvariable=status_var,
        bg="#222222", fg="#CCCCCC",
        font=("Menlo", 12), pady=4,
    ).pack(side=tk.LEFT, padx=20)

    # ── Canvas ──
    canvas_frame = tk.Frame(root)
    canvas_frame.pack(fill=tk.BOTH, expand=True)

    canvas = tk.Canvas(canvas_frame, width=DISPLAY_WIDTH, height=min(display_height, 900),
                       cursor="crosshair")
    h_scroll = tk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=canvas.xview)
    v_scroll = tk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=canvas.yview)
    canvas.configure(xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set)
    h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
    v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
    canvas.pack(fill=tk.BOTH, expand=True)

    photo = ImageTk.PhotoImage(scaled)
    canvas.create_image(0, 0, anchor=tk.NW, image=photo)
    canvas.configure(scrollregion=(0, 0, DISPLAY_WIDTH, display_height))

    def clear_pending_markers():
        for m in pending_marker_items:
            canvas.delete(m)
        pending_marker_items.clear()

    def clear_old_markers():
        for m in old_marker_items:
            canvas.delete(m)
        old_marker_items.clear()

    def draw_pending_marker(cx, cy):
        clear_pending_markers()
        r = 10
        pending_marker_items.append(canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            outline="#FF4444", width=3,
        ))
        pending_marker_items.append(canvas.create_line(
            cx - 15, cy, cx + 15, cy, fill="#FF4444", width=2,
        ))
        pending_marker_items.append(canvas.create_line(
            cx, cy - 15, cx, cy + 15, fill="#FF4444", width=2,
        ))
        name = room_names[current_index[0]] if current_index[0] < len(room_names) else ""
        pending_marker_items.append(canvas.create_text(
            cx + 16, cy - 2, anchor=tk.W, text=name,
            fill="#FF4444", font=("Menlo", 11, "bold"),
        ))

    def update_prompt():
        clear_pending_markers()
        clear_old_markers()
        pending_click[0] = None

        if current_index[0] < len(room_names):
            name = room_names[current_index[0]]
            prompt_var.set(f"Click on: {name}")
            progress_var.set(f"{current_index[0] + 1} of {len(room_names)}")
            status_var.set("Scroll around, then click on the room's box center.")

            # Show current coordinate as blue marker
            old = ROOM_COORDS.get(name)
            if old:
                ox, oy = int(old[0] * scale), int(old[1] * scale)
                r = 8
                old_marker_items.append(canvas.create_oval(
                    ox - r, oy - r, ox + r, oy + r,
                    outline="#4488FF", width=2,
                ))
                old_marker_items.append(canvas.create_text(
                    ox + 12, oy, anchor=tk.W, text="(current)",
                    fill="#4488FF", font=("Menlo", 10),
                ))
                # Scroll to show it
                canvas.xview_moveto(max(0, (ox - 400)) / DISPLAY_WIDTH)
                canvas.yview_moveto(max(0, (oy - 300)) / display_height)
        else:
            prompt_var.set("All done! Close window to save.")
            progress_var.set(f"{len(room_names)} of {len(room_names)}")
            status_var.set("Close the window to write coordinates to map_coords.py.")

    def on_click(event):
        if current_index[0] >= len(room_names):
            return

        cx = canvas.canvasx(event.x)
        cy = canvas.canvasy(event.y)
        full_x = int(cx / scale)
        full_y = int(cy / scale)

        pending_click[0] = (full_x, full_y)
        draw_pending_marker(cx, cy)
        status_var.set(
            f"Placed at ({full_x}, {full_y}). "
            "Click again to reposition, or press Confirm."
        )

    def confirm():
        if current_index[0] >= len(room_names):
            return
        if pending_click[0] is None:
            status_var.set("Click on the map first!")
            return

        name = room_names[current_index[0]]
        full_x, full_y = pending_click[0]
        new_coords[name] = (full_x, full_y)
        print(f"  {name}: ({full_x}, {full_y})")

        # Draw permanent green marker
        cx, cy = int(full_x * scale), int(full_y * scale)
        r = 5
        canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                           fill="#39FF14", outline="white", width=1)

        current_index[0] += 1
        update_prompt()

    def skip():
        if current_index[0] >= len(room_names):
            return
        name = room_names[current_index[0]]
        old = ROOM_COORDS.get(name)
        if old:
            new_coords[name] = old
            print(f"  {name}: ({old[0]}, {old[1]}) [kept]")

            # Draw permanent blue marker for skipped
            cx, cy = int(old[0] * scale), int(old[1] * scale)
            r = 4
            canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                               fill="#4488FF", outline="white", width=1)
        current_index[0] += 1
        update_prompt()

    def undo():
        if current_index[0] > 0:
            current_index[0] -= 1
            name = room_names[current_index[0]]
            if name in new_coords:
                del new_coords[name]
            update_prompt()

    canvas.bind("<Button-1>", on_click)

    confirm_btn = tk.Button(btn_frame, text="Confirm", command=confirm,
                            font=("Menlo", 13, "bold"), bg="#39FF14", fg="#000000",
                            padx=15)
    confirm_btn.pack(side=tk.RIGHT, padx=5)

    skip_btn = tk.Button(btn_frame, text="Skip", command=skip,
                         font=("Menlo", 12), padx=10)
    skip_btn.pack(side=tk.RIGHT, padx=5)

    undo_btn = tk.Button(btn_frame, text="Undo", command=undo,
                         font=("Menlo", 12), padx=10)
    undo_btn.pack(side=tk.RIGHT, padx=5)

    # Keyboard shortcuts
    root.bind("<Return>", lambda e: confirm())
    root.bind("<space>", lambda e: skip())
    root.bind("<BackSpace>", lambda e: undo())

    update_prompt()

    print(f"Calibrating {len(room_names)} rooms.")
    print("  Click to place marker, then Confirm (or Enter).")
    print("  Skip (or Space) to keep current coordinate.")
    print("  Undo (or Backspace) to go back.")
    print()

    root.mainloop()

    # Save results
    if not new_coords:
        print("No coordinates recorded.")
        return

    merged = dict(ROOM_COORDS)
    merged.update(new_coords)

    lines = [
        '"""Pixel coordinates for room labels on zork-1-map-ZUG-1982.jpeg (6517x5030).',
        '',
        'Each entry maps a room name (as output by the game) to the approximate',
        'center (x, y) of that room\'s rectangle on the map image.',
        '"""',
        '',
        'ROOM_COORDS: dict[str, tuple[int, int]] = {',
    ]
    for name in sorted(merged.keys()):
        x, y = merged[name]
        lines.append(f'    "{name}": ({x}, {y}),')
    lines.append('}')
    lines.append('')
    lines.append('')
    lines.append('# Aliases for variant room names the game may output')
    lines.append('_ALIASES: dict[str, str] = {')
    lines.append('    "The Cellar": "Cellar",')
    lines.append('    "Mirror Room (North)": "Mirror Room",')
    lines.append('}')
    lines.append('')
    lines.append('')
    lines.append('def get_room_coords(room_name: str) -> tuple[int, int] | None:')
    lines.append('    """Look up pixel coordinates for a room name. Returns (x, y) or None."""')
    lines.append('    if room_name in ROOM_COORDS:')
    lines.append('        return ROOM_COORDS[room_name]')
    lines.append('    canonical = _ALIASES.get(room_name)')
    lines.append('    if canonical and canonical in ROOM_COORDS:')
    lines.append('        return ROOM_COORDS[canonical]')
    lines.append('    lower = room_name.lower()')
    lines.append('    for name, coords in ROOM_COORDS.items():')
    lines.append('        if name.lower() == lower:')
    lines.append('            return coords')
    lines.append('    return None')
    lines.append('')

    COORDS_FILE.write_text("\n".join(lines))
    print(f"\nSaved {len(merged)} room coordinates to {COORDS_FILE}")


if __name__ == "__main__":
    run_calibration()
