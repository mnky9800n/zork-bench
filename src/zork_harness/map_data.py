"""Static map data for Zork 1.

Each room entry contains:
  exits       - dict mapping direction string to destination room name
  description - brief description of the room
  items       - list of notable items found here

Room names must exactly match the keys in map_coords.py.
"""

ZORK1_MAP: dict[str, dict] = {
    # -------------------------------------------------------------------------
    # Above-ground: House and surroundings
    # -------------------------------------------------------------------------
    "West of House": {
        "exits": {
            "north": "North of House",
            "south": "South of House",
            "east": "Behind House",
            "west": "Forest (1)",
        },
        "description": "You are standing in an open field west of a white house, with a boarded front door.",
        "items": ["mailbox"],
    },
    "North of House": {
        "exits": {
            "west": "West of House",
            "east": "Behind House",
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
            "west": "Forest (1)",
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
    # -------------------------------------------------------------------------
    # Above-ground: Forest and canyon
    # -------------------------------------------------------------------------
    "Forest (1)": {
        "exits": {
            "east": "West of House",
            "north": "Forest Path",
            "south": "Forest (3)",
            "west": "Forest (1)",
        },
        "description": "This is a forest, with trees in all directions. To the east, there appears to be sunlight.",
        "items": [],
    },
    "Forest (2)": {
        "exits": {
            "north": "Clearing (north)",
            "south": "Forest Path",
            "west": "Forest (1)",
            "east": "Forest (4)",
        },
        "description": "This is a dimly lit forest. A path runs south toward the white house.",
        "items": [],
    },
    "Forest (3)": {
        "exits": {
            "north": "Forest (1)",
            "east": "Forest Path",
        },
        "description": "This is a forest, with trees in all directions.",
        "items": [],
    },
    "Forest (4)": {
        "exits": {
            "west": "Forest (2)",
            "south": "Canyon View",
        },
        "description": "This is a forest, with trees in all directions. A path leads south toward a canyon.",
        "items": [],
    },
    "Forest Path": {
        "exits": {
            "west": "Behind House",
            "north": "Forest (2)",
            "east": "Canyon View",
            "south": "Forest (3)",
        },
        "description": "This is a path winding through a dimly lit forest. The path heads north-south here. One particularly large tree with some low branches stands at the edge of the path.",
        "items": [],
    },
    "Up a Tree": {
        "exits": {
            "down": "Forest Path",
        },
        "description": "You are about 10 feet above the ground nestled among some large branches. The bark is quite rough.",
        "items": ["bird's nest", "egg"],
    },
    "Clearing": {
        "exits": {
            "south": "Forest Path",
            "west": "Forest (1)",
            "east": "Canyon View",
        },
        "description": "You are in a small clearing in a well marked forest path that extends to the east and west.",
        "items": [],
    },
    "Clearing (north)": {
        "exits": {
            "south": "Forest (2)",
        },
        "description": "You are in a clearing. A grating is set into the ground.",
        "items": ["grating"],
    },
    "Canyon View": {
        "exits": {
            "west": "Forest Path",
            "down": "Rocky Ledge",
        },
        "description": "You are at the top of the Great Canyon on its west wall. From here there is a marvelous view of the canyon and parts of the Frigid River gorge.",
        "items": [],
    },
    "Rocky Ledge": {
        "exits": {
            "up": "Canyon View",
            "down": "Canyon Bottom",
        },
        "description": "You are on a rocky ledge on the wall of the Great Canyon.",
        "items": [],
    },
    "Canyon Bottom": {
        "exits": {
            "up": "Rocky Ledge",
            "south": "End of Rainbow",
        },
        "description": "You are at the bottom of the Great Canyon. A narrow ledge of rock runs along the river below the falls. The walls of the canyon tower above you.",
        "items": [],
    },
    "End of Rainbow": {
        "exits": {
            "north": "Canyon Bottom",
            "over": "On the Rainbow",
        },
        "description": "You are on a small, rocky beach beside the Frigid River, on which there is a beautiful rainbow. The falls are to the north.",
        "items": ["pot of gold"],
    },
    "On the Rainbow": {
        "exits": {
            "east": "Aragain Falls",
            "west": "End of Rainbow",
        },
        "description": "You are on top of a rainbow. Below you the ground glitters with the many colors of the rainbow. A bridge spans the Frigid River.",
        "items": [],
    },
    "Aragain Falls": {
        "exits": {
            "west": "On the Rainbow",
        },
        "description": "You are at the Aragain Falls. The Frigid River crashes down here into a roiling pool far below. The rainbow arches across to the west.",
        "items": [],
    },
    # -------------------------------------------------------------------------
    # Underground: Below the house
    # -------------------------------------------------------------------------
    "Cellar": {
        "exits": {
            "up": "Living Room",
            "north": "Troll Room",
            "east": "East-West Passage",
        },
        "description": "You are in a dark and damp cellar with a narrow passageway leading north, and a crawlway to the east. On the west is the bottom of a steep metal ramp.",
        "items": [],
    },
    # -------------------------------------------------------------------------
    # Underground: Maze of twisty passages
    # -------------------------------------------------------------------------
    "Troll Room": {
        "exits": {
            "south": "Cellar",
            "east": "East-West Passage",
            "west": "Maze (1)",
        },
        "description": "This is a small room with passages to the east and south and a forbidding hole leading west. Bloodstains and deep scratches (perhaps made by an axe) mar the walls.",
        "items": ["troll", "bloody axe"],
    },
    "Maze (1)": {
        "exits": {
            "east": "Troll Room",
            "north": "Maze (2)",
            "south": "Maze (4)",
            "west": "Maze (3)",
        },
        "description": "You are in a maze of twisty little passages, all alike.",
        "items": [],
    },
    "Maze (2)": {
        "exits": {
            "north": "Maze (1)",
            "east": "Maze (3)",
            "south": "Maze (5)",
            "west": "Maze (2)",
        },
        "description": "You are in a maze of twisty little passages, all alike.",
        "items": [],
    },
    "Maze (3)": {
        "exits": {
            "east": "Maze (1)",
            "north": "Maze (2)",
            "south": "Maze (6)",
            "west": "Maze (3)",
            "up": "Maze (4)",
        },
        "description": "You are in a maze of twisty little passages, all alike.",
        "items": [],
    },
    "Maze (4)": {
        "exits": {
            "north": "Maze (1)",
            "east": "Maze (5)",
            "south": "Maze (4)",
            "down": "Maze (3)",
        },
        "description": "You are in a maze of twisty little passages, all alike.",
        "items": ["skeleton", "knife"],
    },
    "Maze (5)": {
        "exits": {
            "north": "Maze (2)",
            "east": "Maze (6)",
            "south": "Maze (7)",
            "west": "Maze (4)",
        },
        "description": "You are in a maze of twisty little passages, all alike.",
        "items": [],
    },
    "Maze (6)": {
        "exits": {
            "north": "Maze (3)",
            "west": "Maze (5)",
            "east": "Maze (8)",
            "south": "Maze (9)",
        },
        "description": "You are in a maze of twisty little passages, all alike.",
        "items": [],
    },
    "Maze (7)": {
        "exits": {
            "north": "Maze (5)",
            "east": "Maze (8)",
            "south": "Maze (10)",
            "west": "Maze (7)",
        },
        "description": "You are in a maze of twisty little passages, all alike.",
        "items": [],
    },
    "Maze (8)": {
        "exits": {
            "west": "Maze (6)",
            "north": "Maze (7)",
            "south": "Maze (11)",
            "east": "Dead End",
        },
        "description": "You are in a maze of twisty little passages, all alike.",
        "items": [],
    },
    "Maze (9)": {
        "exits": {
            "north": "Maze (6)",
            "east": "Maze (10)",
            "south": "Maze (12)",
            "west": "Maze (9)",
        },
        "description": "You are in a maze of twisty little passages, all alike.",
        "items": [],
    },
    "Maze (10)": {
        "exits": {
            "north": "Maze (7)",
            "west": "Maze (9)",
            "east": "Maze (11)",
            "south": "Maze (13)",
        },
        "description": "You are in a maze of twisty little passages, all alike.",
        "items": [],
    },
    "Maze (11)": {
        "exits": {
            "north": "Maze (8)",
            "west": "Maze (10)",
            "south": "Maze (14)",
            "east": "Maze (11)",
        },
        "description": "You are in a maze of twisty little passages, all alike.",
        "items": [],
    },
    "Maze (12)": {
        "exits": {
            "north": "Maze (9)",
            "east": "Maze (13)",
            "south": "Maze (12)",
            "west": "Maze (15)",
        },
        "description": "You are in a maze of twisty little passages, all alike.",
        "items": [],
    },
    "Maze (13)": {
        "exits": {
            "north": "Maze (10)",
            "west": "Maze (12)",
            "south": "Maze (14)",
            "east": "Maze (13)",
        },
        "description": "You are in a maze of twisty little passages, all alike.",
        "items": [],
    },
    "Maze (14)": {
        "exits": {
            "north": "Maze (11)",
            "west": "Maze (13)",
            "east": "Maze (15)",
            "south": "Grating Room",
        },
        "description": "You are in a maze of twisty little passages, all alike.",
        "items": [],
    },
    "Maze (15)": {
        "exits": {
            "east": "Maze (12)",
            "west": "Maze (14)",
            "south": "Dead End",
        },
        "description": "You are in a maze of twisty little passages, all alike.",
        "items": [],
    },
    "Maze": {
        "exits": {
            "north": "Maze (1)",
        },
        "description": "You are in a maze of twisty little passages, all different.",
        "items": [],
    },
    "Dead End": {
        "exits": {
            "west": "Maze (8)",
            "north": "Maze (15)",
        },
        "description": "You have reached a dead end.",
        "items": ["bag of coins"],
    },
    # -------------------------------------------------------------------------
    # Underground: East passages (Cellar area)
    # -------------------------------------------------------------------------
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
            "northeast": "Chasm",
        },
        "description": "You are in a circular room with passages leading northwest and east, a staircase above, and a hole to the south.",
        "items": [],
    },
    "Loud Room": {
        "exits": {
            "south": "Round Room",
            "east": "Narrow Passage",
        },
        "description": "This is a large room with a central pillar of rock. The floor is covered with a fine layer of sand. The room echoes with the sound of rushing water.",
        "items": ["platinum bar"],
    },
    "Narrow Passage": {
        "exits": {
            "west": "Loud Room",
            "east": "Mirror Room",
        },
        "description": "This is a narrow east-west passage.",
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
    "Engravings Cave": {
        "exits": {
            "west": "Round Room",
            "east": "Chasm",
        },
        "description": "You are in a cave whose walls are covered with ancient engravings.",
        "items": [],
    },
    "Chasm": {
        "exits": {
            "west": "Engravings Cave",
            "southwest": "Round Room",
            "northeast": "Deep Canyon",
        },
        "description": "You are at the Chasm. A chasm runs southwest to northeast, and a stone bridge crosses the chasm.",
        "items": [],
    },
    "Deep Canyon": {
        "exits": {
            "southwest": "Chasm",
            "north": "Shaft Room",
        },
        "description": "You are at the top of the Great Canyon on its east wall. Looking down into the canyon you see nothing but darkness.",
        "items": [],
    },
    "Shaft Room": {
        "exits": {
            "south": "Deep Canyon",
            "down": "Smelly Room",
        },
        "description": "This is a room with a shaft leading down into the earth. A ladder hangs from the wall.",
        "items": [],
    },
    "Smelly Room": {
        "exits": {
            "up": "Shaft Room",
            "east": "Gas Room",
            "south": "Coal Mine (1)",
        },
        "description": "This is a small room. The air here smells of coal and dust.",
        "items": [],
    },
    "Gas Room": {
        "exits": {
            "west": "Smelly Room",
        },
        "description": "This is a small room. The air smells strongly of sulfur.",
        "items": [],
    },
    "Coal Mine (1)": {
        "exits": {
            "north": "Smelly Room",
            "east": "Coal Mine (2)",
            "south": "Coal Mine (4)",
        },
        "description": "You are in a coal mine. The passages are carved from solid coal.",
        "items": [],
    },
    "Coal Mine (2)": {
        "exits": {
            "west": "Coal Mine (1)",
            "south": "Coal Mine (3)",
        },
        "description": "You are in a coal mine. The passages are dimly lit by small ventilation shafts.",
        "items": [],
    },
    "Coal Mine (3)": {
        "exits": {
            "north": "Coal Mine (2)",
            "west": "Coal Mine (4)",
        },
        "description": "You are in a coal mine. Debris litters the floor.",
        "items": ["coal"],
    },
    "Coal Mine (4)": {
        "exits": {
            "north": "Coal Mine (1)",
            "east": "Coal Mine (3)",
        },
        "description": "You are in a coal mine with passages leading north and east.",
        "items": [],
    },
    # -------------------------------------------------------------------------
    # Underground: Torch Room and Temple area
    # -------------------------------------------------------------------------
    "Torch Room": {
        "exits": {
            "up": "Dome Room",
            "south": "Temple",
            "west": "Altar",
        },
        "description": "This is a large room with a prominent doorway leading to a room to the south. Above the doorway is an ancient inscription which says 'This is the Torch Room.'",
        "items": ["torch"],
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
            "west": "Cave (near Hades)",
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
    "Cave (near Hades)": {
        "exits": {
            "east": "Altar",
            "west": "Entrance to Hades",
        },
        "description": "You are in a cave. The cave continues to the west toward what appears to be a ghostly gate.",
        "items": [],
    },
    "Entrance to Hades": {
        "exits": {
            "east": "Cave (near Hades)",
            "north": "Land of the Dead",
        },
        "description": "You are at the entrance to Hades. A large gate stands to the west, and spirits drift by.",
        "items": ["spirits"],
    },
    "Land of the Dead": {
        "exits": {
            "south": "Entrance to Hades",
        },
        "description": "You have entered the Land of the Dead. This is a bleak, ghostly place with no visible exits other than back south.",
        "items": [],
    },
    "Winding Passage": {
        "exits": {
            "north": "Cave (near Hades)",
            "south": "Damp Cave",
        },
        "description": "This is a winding passage leading through the rock.",
        "items": [],
    },
    "Damp Cave": {
        "exits": {
            "north": "Winding Passage",
            "east": "East of Chasm",
        },
        "description": "This is a damp cave with moisture dripping from the ceiling.",
        "items": [],
    },
    "East of Chasm": {
        "exits": {
            "west": "Damp Cave",
            "north": "Gallery",
        },
        "description": "You are on the east side of a chasm that cuts across the land.",
        "items": [],
    },
    "Gallery": {
        "exits": {
            "south": "East of Chasm",
            "north": "Treasure Room",
        },
        "description": "This is a gallery of some sort. The walls are adorned with paintings.",
        "items": ["painting"],
    },
    "Treasure Room": {
        "exits": {
            "south": "Gallery",
        },
        "description": "This is a large room, possibly an old throne room. A huge treasure chest sits in the center.",
        "items": ["treasure chest", "jewels"],
    },
    "Strange Passage": {
        "exits": {
            "east": "Mirror Room (South)",
            "west": "Cyclops Room",
        },
        "description": "This is a strange passage, neither fully cave nor corridor.",
        "items": [],
    },
    "Cyclops Room": {
        "exits": {
            "east": "Strange Passage",
            "up": "Living Room",
        },
        "description": "This room has an obviously long-disused exit to the east. In the corner of the room is a cyclops who seems to be studying you with its single eye.",
        "items": ["cyclops"],
    },
    "Mirror Room": {
        "exits": {
            "west": "Narrow Passage",
            "south": "Mirror Room (South)",
        },
        "description": "This is a room that is quite unlike the others you have seen. The walls are papered with mirrors.",
        "items": [],
    },
    "Mirror Room (South)": {
        "exits": {
            "north": "Mirror Room",
            "west": "Strange Passage",
        },
        "description": "This is a room that appears to be the mirror image of another room. The walls are papered with mirrors.",
        "items": [],
    },
    # -------------------------------------------------------------------------
    # Underground: Grating Room
    # -------------------------------------------------------------------------
    "Grating Room": {
        "exits": {
            "north": "Maze (14)",
            "up": "Clearing (north)",
        },
        "description": "You are in a small room. A grating in the ceiling leads to a clearing above.",
        "items": ["grating"],
    },
    # -------------------------------------------------------------------------
    # Underground: North-South passages (deep dungeon)
    # -------------------------------------------------------------------------
    "North-South Passage": {
        "exits": {
            "north": "Chasm",
            "south": "East of Chasm",
        },
        "description": "This is a north-south passage. The walls are rough-hewn rock.",
        "items": [],
    },
    # -------------------------------------------------------------------------
    # Underground: Reservoir and dam area
    # -------------------------------------------------------------------------
    "Dam Lobby": {
        "exits": {
            "south": "Dam",
            "east": "Maintenance Room",
        },
        "description": "This is the lobby of the Flood Control Dam. Informational pamphlets about the dam line the walls.",
        "items": [],
    },
    "Dam": {
        "exits": {
            "north": "Dam Lobby",
            "south": "Dam Base",
            "west": "Maintenance Room",
            "east": "Reservoir South",
        },
        "description": "You are standing on the top of Flood Control Dam #3, which was quite a tourist attraction in times far distant. The reservoir to the north is almost empty.",
        "items": ["bolt", "wrench"],
    },
    "Dam Base": {
        "exits": {
            "north": "Dam",
            "east": "Frigid River (1)",
        },
        "description": "You are at the base of Flood Control Dam #3. The dam is 100 feet high here and made of concrete.",
        "items": [],
    },
    "Maintenance Room": {
        "exits": {
            "west": "Dam",
            "east": "Dam Lobby",
        },
        "description": "This is the maintenance room for the dam. Assorted tools and machinery fill the room.",
        "items": ["wrench", "screwdriver"],
    },
    "Reservoir": {
        "exits": {
            "south": "Reservoir South",
            "east": "Reservoir North",
        },
        "description": "You are on the surface of the reservoir. The dam is to the south.",
        "items": [],
    },
    "Reservoir South": {
        "exits": {
            "west": "Dam",
            "north": "Reservoir",
        },
        "description": "You are on the southern shore of the Reservoir.",
        "items": [],
    },
    "Reservoir North": {
        "exits": {
            "west": "Reservoir",
            "south": "Reservoir",
        },
        "description": "You are on the northern shore of the Reservoir. The water is quite deep here.",
        "items": [],
    },
    "Stream View": {
        "exits": {
            "north": "Stream",
            "south": "Dam Base",
        },
        "description": "You are at a point where the stream passes by. The stream flows to the north.",
        "items": [],
    },
    "Stream": {
        "exits": {
            "south": "Stream View",
            "north": "Reservoir South",
        },
        "description": "You are in a shallow stream. The water is crystal clear.",
        "items": [],
    },
    # -------------------------------------------------------------------------
    # Frigid River (raft passages)
    # -------------------------------------------------------------------------
    "Frigid River (1)": {
        "exits": {
            "west": "Dam Base",
            "south": "Frigid River (2)",
        },
        "description": "You are in the Frigid River. The current is strong and the water is icy cold.",
        "items": [],
    },
    "Frigid River (2)": {
        "exits": {
            "north": "Frigid River (1)",
            "south": "Frigid River (3)",
            "east": "White Cliffs Beach",
        },
        "description": "You are in the Frigid River. The white cliffs of the canyon loom to the east.",
        "items": [],
    },
    "Frigid River (3)": {
        "exits": {
            "north": "Frigid River (2)",
            "south": "Frigid River (4)",
            "east": "White Cliffs Beach (South)",
        },
        "description": "You are in the Frigid River. The current sweeps you southward.",
        "items": [],
    },
    "Frigid River (4)": {
        "exits": {
            "north": "Frigid River (3)",
            "south": "Frigid River (5)",
            "west": "Sandy Beach",
        },
        "description": "You are in the Frigid River. A sandy beach lies to the west.",
        "items": [],
    },
    "Frigid River (5)": {
        "exits": {
            "north": "Frigid River (4)",
            "east": "Shore",
            "south": "Aragain Falls",
        },
        "description": "You are in the Frigid River. The roar of the falls grows louder ahead.",
        "items": [],
    },
    "White Cliffs Beach": {
        "exits": {
            "west": "Frigid River (2)",
            "south": "White Cliffs Beach (South)",
        },
        "description": "You are on a small beach at the base of the white cliffs. The Frigid River laps at your feet.",
        "items": [],
    },
    "White Cliffs Beach (South)": {
        "exits": {
            "north": "White Cliffs Beach",
            "west": "Frigid River (3)",
        },
        "description": "You are on the southern portion of the beach at the foot of the white cliffs.",
        "items": [],
    },
    "Sandy Beach": {
        "exits": {
            "east": "Frigid River (4)",
            "west": "Sandy Cave",
        },
        "description": "You are on a sandy beach near the Frigid River. A cave entrance lies to the west.",
        "items": [],
    },
    "Sandy Cave": {
        "exits": {
            "east": "Sandy Beach",
        },
        "description": "This is a small sandy cave near the river bank.",
        "items": ["trunk"],
    },
    "Shore": {
        "exits": {
            "west": "Frigid River (5)",
        },
        "description": "You are on the eastern shore of the Frigid River, near the falls.",
        "items": [],
    },
    # -------------------------------------------------------------------------
    # Underground: Mine and upper areas
    # -------------------------------------------------------------------------
    "Mine Entrance": {
        "exits": {
            "south": "Squeaky Room",
            "down": "Smelly Room",
        },
        "description": "You are at the entrance to a mine. The mouth of the mine yawns to the south.",
        "items": [],
    },
    "Squeaky Room": {
        "exits": {
            "north": "Mine Entrance",
            "east": "Bat Room",
        },
        "description": "You are in a room whose walls make a persistent squeaking sound.",
        "items": [],
    },
    "Bat Room": {
        "exits": {
            "west": "Squeaky Room",
            "east": "Cold Passage",
        },
        "description": "You are in a small room. A colony of bats roosts from the ceiling.",
        "items": ["bats"],
    },
    "Cold Passage": {
        "exits": {
            "west": "Bat Room",
            "south": "Slide Room",
        },
        "description": "This is a cold, narrow passage. A frigid draft blows from somewhere to the south.",
        "items": [],
    },
    "Slide Room": {
        "exits": {
            "north": "Cold Passage",
            "down": "Twisting Passage",
        },
        "description": "This is a room with a sloping floor that leads down into darkness.",
        "items": [],
    },
    "Twisting Passage": {
        "exits": {
            "up": "Slide Room",
            "south": "Mirror Room",
        },
        "description": "This is a twisting passage that winds downward through the rock.",
        "items": [],
    },
    "Drafty Room": {
        "exits": {
            "south": "Machine Room",
            "east": "Ladder Top",
        },
        "description": "This is a room with a strong draft coming from the south. Ladder rungs are set into the wall to the east.",
        "items": [],
    },
    "Ladder Top": {
        "exits": {
            "west": "Drafty Room",
            "down": "Ladder Bottom",
        },
        "description": "You are at the top of a long ladder. Below you lies darkness.",
        "items": [],
    },
    "Ladder Bottom": {
        "exits": {
            "up": "Ladder Top",
            "east": "Timber Room",
        },
        "description": "You are at the bottom of a long ladder. Passages lead east.",
        "items": [],
    },
    "Timber Room": {
        "exits": {
            "west": "Ladder Bottom",
        },
        "description": "This is a room reinforced with timber beams. The beams look old and precarious.",
        "items": [],
    },
    # -------------------------------------------------------------------------
    # Underground: Machine Room / Studio area
    # -------------------------------------------------------------------------
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
            "north": "Drafty Room",
        },
        "description": "This is a large room full of assorted machinery, all of which is in a state of extreme disrepair.",
        "items": ["machine", "switchboard"],
    },
    # -------------------------------------------------------------------------
    # Underground: Atlantis and cave area
    # -------------------------------------------------------------------------
    "Cave (near Atlantis)": {
        "exits": {
            "east": "Atlantis Room",
            "west": "Twisting Passage",
        },
        "description": "This is a cave whose ceiling sparkles with reflected light from an underground lake to the east.",
        "items": [],
    },
    "Atlantis Room": {
        "exits": {
            "west": "Cave (near Atlantis)",
        },
        "description": "This is an ancient undersea room, presumably once part of the legendary Atlantis.",
        "items": ["Poseidon figurine"],
    },
}
