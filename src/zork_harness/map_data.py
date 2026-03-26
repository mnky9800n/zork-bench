"""Static map data for Zork 1.

Each room entry contains:
  exits       - dict mapping direction string to destination room name
  description - brief description of the room
  items       - list of notable items found here
"""

ZORK1_MAP: dict[str, dict] = {
    "West of House": {
        "exits": {
            "north": "North of House",
            "south": "South of House",
            "east": "Behind House",
            "west": "Forest",
        },
        "description": "You are standing in an open field west of a white house, with a boarded front door.",
        "items": ["mailbox"],
    },
    "North of House": {
        "exits": {
            "west": "West of House",
            "east": "North of House",
            "south": "West of House",
        },
        "description": "You are facing the north side of a white house. There is no door here, and all the windows are boarded up.",
        "items": [],
    },
    "South of House": {
        "exits": {
            "west": "West of House",
            "east": "Behind House",
        },
        "description": "You are facing the south side of a white house. There is no door here, and all the windows are boarded.",
        "items": [],
    },
    "Behind House": {
        "exits": {
            "north": "North of House",
            "south": "South of House",
            "west": "West of House",
            "in": "Kitchen",
            "east": "Forest Path",
        },
        "description": "You are behind the white house. A path leads into the forest to the east. In one corner of the house there is a small window which is slightly ajar.",
        "items": ["window (slightly open)"],
    },
    "Kitchen": {
        "exits": {
            "west": "Living Room",
            "up": "Attic",
            "out": "Behind House",
        },
        "description": "You are in the kitchen of the white house. A table seems to have been used recently for the preparation of food.",
        "items": ["table", "sack", "water bottle", "knife"],
    },
    "Living Room": {
        "exits": {
            "east": "Kitchen",
            "west": "Forest",
            "down": "Cellar",
        },
        "description": "You are in the living room. There is a doorway to the east, a wooden door with strange gothic lettering to the west, and a large oriental rug in the center of the room.",
        "items": ["trophy case", "battery-powered lamp", "rug", "sword"],
    },
    "Attic": {
        "exits": {
            "down": "Kitchen",
        },
        "description": "This is the attic. The only exit is a stairway leading down.",
        "items": ["rope", "nasty knife"],
    },
    "Cellar": {
        "exits": {
            "up": "Living Room",
            "north": "Troll Room",
            "east": "East-West Passage",
        },
        "description": "You are in a dark and damp cellar with a narrow passageway leading north, and a crawlway to the east. On the west is the bottom of a steep metal ramp.",
        "items": [],
    },
    "Troll Room": {
        "exits": {
            "south": "Cellar",
            "east": "East-West Passage",
            "west": "Maze",
        },
        "description": "This is a small room with passages to the east and south and a forbidding hole leading west. Bloodstains and deep scratches (perhaps made by an axe) mar the walls.",
        "items": ["troll", "bloody axe"],
    },
    "East-West Passage": {
        "exits": {
            "west": "Troll Room",
            "east": "Round Room",
            "up": "Cellar",
        },
        "description": "This is a narrow east-west passageway. There is a narrow stairway leading up at the north end of the room.",
        "items": [],
    },
    "Round Room": {
        "exits": {
            "west": "East-West Passage",
            "north": "Loud Room",
            "south": "Dome Room",
            "east": "Engravings Cave",
        },
        "description": "You are in a circular room with passages leading northwest and east, a staircase above, and a hole to the south.",
        "items": [],
    },
    "Dome Room": {
        "exits": {
            "north": "Round Room",
            "down": "Torch Room",
        },
        "description": "You are at the top of the Dome. The room is thirty feet high and has a narrow ledge about halfway up. Stairs lead down into darkness.",
        "items": [],
    },
    "Torch Room": {
        "exits": {
            "up": "Dome Room",
            "south": "Temple",
            "west": "Altar",
        },
        "description": "This is a large room with a prominent doorway leading to a room to the south. Above the doorway is an ancient inscription which says 'This is the Torch Room.'",
        "items": ["torch"],
    },
    "Loud Room": {
        "exits": {
            "south": "Round Room",
            "east": "Narrow Passage",
        },
        "description": "This is a large room with a central pillar of rock. The floor is covered with a fine layer of sand. The room echoes with the sound of rushing water.",
        "items": ["platinum bar"],
    },
    "Temple": {
        "exits": {
            "north": "Torch Room",
            "up": "Egyptian Room",
            "east": "Altar",
        },
        "description": "This is the Temple. The walls are covered with ancient inscriptions. A stairway leads up to the north.",
        "items": [],
    },
    "Altar": {
        "exits": {
            "east": "Temple",
            "west": "Cave",
        },
        "description": "This is the Altar. The altar is made of white alabaster.",
        "items": ["candles", "prayer rug"],
    },
    "Egyptian Room": {
        "exits": {
            "down": "Temple",
        },
        "description": "You are in a room which is painted to resemble an Egyptian tomb. There are several sarcophagi here.",
        "items": ["Egyptian coin"],
    },
    "Forest": {
        "exits": {
            "east": "West of House",
            "north": "Forest Path",
            "south": "Forest",
        },
        "description": "This is a forest, with trees in all directions. To the east, there appears to be sunlight.",
        "items": [],
    },
    "Forest Path": {
        "exits": {
            "west": "Behind House",
            "north": "Clearing",
            "east": "Canyon View",
            "south": "Forest",
        },
        "description": "This is a path winding through a dimly lit forest. The path heads north-south here. One particularly large tree with some low branches stands at the edge of the path.",
        "items": [],
    },
    "Clearing": {
        "exits": {
            "south": "Forest Path",
            "west": "Forest",
            "east": "Canyon View",
        },
        "description": "You are in a small clearing in a well marked forest path that extends to the east and west.",
        "items": [],
    },
    "Canyon View": {
        "exits": {
            "west": "Forest Path",
            "down": "Rocky Ledge",
        },
        "description": "You are at the top of the Great Canyon on its west wall. From here there is a marvelous view of the canyon and parts of the Frigid River gorge.",
        "items": [],
    },
    "Dam": {
        "exits": {
            "north": "Lobby",
            "south": "Dam Base",
            "west": "Maintenance Room",
            "east": "Reservoir South",
        },
        "description": "You are standing on the top of the Flood Control Dam #3, which was quite a tourist attraction in times far distant. The reservoir to the north is almost empty.",
        "items": ["bolt", "wrench"],
    },
    "Dam Base": {
        "exits": {
            "north": "Dam",
            "east": "Frigid River",
        },
        "description": "You are at the base of Flood Control Dam #3. The dam is 100 feet high here and made of concrete.",
        "items": [],
    },
    "Reservoir": {
        "exits": {
            "south": "Dam",
            "east": "Reservoir North",
        },
        "description": "You are on the surface of the reservoir. The dam is to the south.",
        "items": [],
    },
    "Maze (twisty passages)": {
        "exits": {
            "east": "Troll Room",
        },
        "description": "You are in a maze of twisty little passages, all alike. This is a well-known maze; mapping it requires dropping items to mark visited rooms.",
        "items": [],
    },
    "Studio": {
        "exits": {
            "north": "Machine Room",
            "south": "Dam",
        },
        "description": "This is what appears to have been an artist's studio. The walls and floors are splattered with paints of 69 brilliant colors.",
        "items": ["skeleton", "painting"],
    },
    "Machine Room": {
        "exits": {
            "south": "Studio",
        },
        "description": "This is a large room full of assorted machinery, all of which is in a state of extreme disrepair.",
        "items": ["machine", "switchboard"],
    },
}
