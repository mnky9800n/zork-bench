"""Pixel coordinates for room labels on zork-1-map-ZUG-1982.jpeg (6517x5030).

Each entry maps a room name (as output by the game) to the approximate
center (x, y) of that room's rectangle on the map image.

Coordinates were measured by cropping tight sections around each box
and computing: full_x = crop_offset_x + box_center_in_crop_x.
"""

ROOM_COORDS: dict[str, tuple[int, int]] = {
    # ── LEFT PAGE: House area ──
    # Measured from tight box crops
    "West of House": (610, 1480),
    "North of House": (1150, 1020),
    "Living Room": (1075, 1520),
    "Kitchen": (1325, 1520),
    "Attic": (1310, 1310),
    "Behind House": (1680, 1510),
    "South of House": (1150, 1960),

    # ── LEFT PAGE: Forest / Canyon ──
    # Measured from crop (700, 500) and crop (1600, 500)
    "Forest Path": (1120, 790),
    "Up a Tree": (950, 600),
    "Forest": (1850, 620),
    "Clearing": (1920, 1020),
    "Canyon View": (2200, 1330),
    "Rocky Ledge": (2340, 1700),
    "Canyon Bottom": (2350, 1950),

    # ── LEFT PAGE: Maze area ──
    "Maze": (2250, 4400),
    "Dead End": (2850, 3900),

    # ── RIGHT PAGE: Bat Room / Slide / Mine Entrance ──
    # Measured from crop (3600, 600, 4600, 2000)
    "Bat Room": (3880, 840),
    "Squeaky Room": (3820, 1080),
    "Mine Entrance": (4020, 1080),
    "Slide Room": (3940, 1320),
    # Measured from wider crop (3500, 500, 4800, 2100)
    "Cold Passage": (4520, 1400),
    "Mirror Room": (4500, 1650),       # Mirror Room (North)
    "Twisting Passage": (4480, 1850),

    # ── RIGHT PAGE: Coal Mine area ──
    # Measured from crop (4900, 200, 6400, 1500)
    "Gas Room": (5100, 430),
    "Smelly Room": (5120, 630),
    "Coal Mine": (5430, 600),           # Coal Mine (1)
    "Shaft Room": (5100, 880),
    "Ladder Top": (5950, 950),
    "Ladder Bottom": (5950, 1140),
    "Drafty Room": (5150, 1200),
    "Timber Room": (5420, 1200),
    "Machine Room": (5150, 1400),

    # ── RIGHT PAGE: Stream / Reservoir / Dam ──
    # Measured from crop (4200, 2400, 5000, 2900) and (4700, 2300, 5800, 3000)
    "Stream": (4400, 2640),
    "Reservoir": (4820, 2600),
    "Stream View": (4400, 2800),
    "Reservoir North": (4800, 2360),
    "Reservoir South": (4820, 2820),
    "Dam Lobby": (5600, 2360),
    "Dam": (5430, 2620),
    "Dam Base": (5400, 2850),

    # ── RIGHT PAGE: Chasm / North-South / Loud Room area ──
    # Measured from crop (4400, 2700, 5200, 3500)
    "Chasm": (4650, 2970),
    "Deep Canyon": (4900, 2970),
    "North-South Passage": (4680, 3200),
    "Loud Room": (4950, 3350),
    "Damp Cave": (5200, 3380),

    # ── RIGHT PAGE: Grating Room ──
    # Measured from crop (3400, 2600, 4100, 3200)
    "Grating Room": (3880, 3080),

    # ── RIGHT PAGE: Underground central ──
    # Measured from crop (3400, 3300, 5000, 4000)
    "Troll Room": (3740, 3640),
    "East-West Passage": (3960, 3640),
    "Round Room": (4400, 3550),
    "Cellar": (3860, 3780),
    "Studio": (4080, 3780),

    # ── RIGHT PAGE: Cyclops / Strange / Treasure ──
    # Measured from crop (3200, 3600, 4000, 4200)
    "Cyclops Room": (3390, 3880),
    "Strange Passage": (3630, 3880),
    "Treasure Room": (3390, 4110),

    # ── RIGHT PAGE: Narrow / Engravings / Mirror(S) / Gallery ──
    # Measured from crop (4300, 3500, 5100, 4300)
    "Narrow Passage": (4530, 3750),
    "Engravings Cave": (4820, 3750),
    "Mirror Room (South)": (4550, 3970),
    "Gallery": (4380, 4070),
    "East of Chasm": (3880, 4070),
    "Winding Passage": (4550, 4100),

    # ── RIGHT PAGE: Dome / Torch / Temple / Egyptian ──
    # Measured from crop (4600, 3600, 5600, 4500)
    "Dome Room": (5130, 3800),
    "Torch Room": (5080, 3980),
    "Cave": (4720, 4140),
    "Temple": (5030, 4140),
    "Egyptian Room": (5300, 4140),
    "Altar": (4800, 4300),
    "Entrance to Hades": (4720, 4300),
    "Land of the Dead": (5000, 4450),

    # ── RIGHT PAGE: White Cliffs / Frigid River ──
    # Measured from crop (5200, 2700, 6500, 4300)
    "White Cliffs Beach": (5450, 3230),       # North
    "White Cliffs Beach (South)": (5450, 3470),
    "Frigid River": (5750, 2880),              # Section 1
    "Sandy Cave": (6150, 3200),
    "Sandy Beach": (6100, 3460),
    "Shore": (6150, 3620),

    # ── RIGHT PAGE: Bottom south area ──
    "Aragain Falls": (6250, 4250),
    "On the Rainbow": (5950, 4300),
    "End of Rainbow": (5650, 4300),
}

# Aliases for variant room names the game may output
_ALIASES: dict[str, str] = {
    "The Cellar": "Cellar",
    "Mirror Room (North)": "Mirror Room",
}


def get_room_coords(room_name: str) -> tuple[int, int] | None:
    """Look up pixel coordinates for a room name. Returns (x, y) or None."""
    if room_name in ROOM_COORDS:
        return ROOM_COORDS[room_name]
    canonical = _ALIASES.get(room_name)
    if canonical and canonical in ROOM_COORDS:
        return ROOM_COORDS[canonical]
    lower = room_name.lower()
    for name, coords in ROOM_COORDS.items():
        if name.lower() == lower:
            return coords
    return None
