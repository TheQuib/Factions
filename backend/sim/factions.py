import random

MAP_W = 1200
MAP_H = 820

# --- Timing constants (game-seconds) ---
# Default game speed: 0.5 game-sec / real-sec  →  each of these is ~2x the original value
# so a battle plays out over ~30-60 real minutes, with titans appearing after ~4 hours.
TITAN_TIME      = 7200   # ~4 real hours at default speed
TOWER_EXPIRE    = 4200   # ~2.3 real hours
RESTART_DELAY   = 120    # 4 real minutes between games
PASSIVE_GOLD    = 10
BUILD_GOLD      = 2.5
SWARM_THRESHOLD = 9
MAX_INC_BLDG    = 3
MAX_DEF_BLDG    = 2
MAX_SPECIAL     = 2
MAX_UNITS_PER_FACTION = 38
PANEL_GRACE     = 35

# Server tick / speed settings
TICK_INTERVAL   = 0.033    # real-seconds between simulation ticks (5 Hz)
GAME_SPEED      = 0.5    # game-seconds advanced per real-second
# Each tick: dt = GAME_SPEED * TICK_INTERVAL = 0.1 game-seconds

STARTS = [[160, 160], [600, 130], [1040, 160], [160, 660], [600, 690], [1040, 660]]

ALL_FACTIONS = {
    'red':    {'id': 'red',    'name': 'THE HIVE',        'color': '#D44040', 'lo': '#420A0A', 'hi': '#FF5555'},
    'blue':   {'id': 'blue',   'name': 'MAGE COUNCIL',    'color': '#5090E8', 'lo': '#0E2255', 'hi': '#88BBFF'},
    'green':  {'id': 'green',  'name': 'SYLVAN ELVES',    'color': '#44CC55', 'lo': '#0E3818', 'hi': '#88FF99'},
    'yellow': {'id': 'yellow', 'name': 'PALADIN ORDER',   'color': '#E8C030', 'lo': '#4A3C08', 'hi': '#FFE060'},
    'steel':  {'id': 'steel',  'name': 'IRON LEGION',     'color': '#9AAABB', 'lo': '#2A3040', 'hi': '#DDEEFF'},
    'purp':   {'id': 'purp',   'name': 'SHADOW GUILD',    'color': '#AA44CC', 'lo': '#1A0830', 'hi': '#DD88FF'},
    'cyan':   {'id': 'cyan',   'name': 'STORM RIDERS',    'color': '#22CCCC', 'lo': '#082830', 'hi': '#88FFFF'},
    'bone':   {'id': 'bone',   'name': 'BONE COURT',      'color': '#C8C080', 'lo': '#282410', 'hi': '#FFFFC0'},
    'ice':    {'id': 'ice',    'name': 'FROST COVENANT',  'color': '#88CCFF', 'lo': '#0A1830', 'hi': '#CCEEFF'},
    'olive':  {'id': 'olive',  'name': 'FUNGAL COLONY',   'color': '#88AA22', 'lo': '#1A2008', 'hi': '#CCEE44'},
    'orange': {'id': 'orange', 'name': 'VOLCANIC CLAN',   'color': '#FF7722', 'lo': '#3A1008', 'hi': '#FFAA44'},
    'gold':   {'id': 'gold',   'name': 'CELESTIAL CHOIR', 'color': '#FFD700', 'lo': '#3A3000', 'hi': '#FFEEAA'},
    'teal':   {'id': 'teal',   'name': 'DEEP RAIDERS',    'color': '#22AAAA', 'lo': '#082020', 'hi': '#66DDDD'},
    'crim':   {'id': 'crim',   'name': 'BLOOD PACT',      'color': '#CC2222', 'lo': '#300808', 'hi': '#FF6666'},
    'slate':  {'id': 'slate',  'name': 'GOLEM WORKS',     'color': '#7788AA', 'lo': '#1A2030', 'hi': '#AABBCC'},
    'rose':   {'id': 'rose',   'name': 'DREAM WEAVERS',   'color': '#EE88BB', 'lo': '#3A1030', 'hi': '#FFBBDD'},
}

UTYPES = {
    'hive_swarm':    {'hp': 10,   'dmg': 1,   'spd': 75,  'rng': 18,  'atk_spd': 0.25, 'size': 5,  'cost': 2},
    'hive_soldier':  {'hp': 75,   'dmg': 15,  'spd': 50,  'rng': 22,  'atk_spd': 1.0,  'size': 7,  'cost': 35},
    'hive_host':     {'hp': 90,   'dmg': 0,   'spd': 10,  'rng': 115, 'atk_spd': 10.0, 'size': 9,  'cost': 50, 'spawns': 'hive_mite'},
    'hive_mite':     {'hp': 5,    'dmg': 50,  'spd': 25,  'rng': 14,  'atk_spd': 1.0,  'size': 3,  'cost': 0,  'is_bomber': True, 'aoe': 38},
    'hive_builder':  {'hp': 25,   'dmg': 0,   'spd': 40,  'rng': 0,   'size': 5,        'cost': 28, 'is_builder': True, 'build_time': 9,  'b_type': 'tumor'},
    'brood_bug':     {'hp': 22,   'dmg': 6,   'spd': 58,  'rng': 18,  'atk_spd': 0.6,  'size': 4,  'cost': 0},
    'wiz_fire':      {'hp': 55,   'dmg': 5,   'spd': 10,  'rng': 100, 'atk_spd': 1.5,  'size': 6,  'cost': 25, 'aoe': 10},
    'wiz_storm':     {'hp': 55,   'dmg': 5,   'spd': 10,  'rng': 100, 'atk_spd': 3.0,  'size': 6,  'cost': 45, 'chains': 3},
    'wiz_necro':     {'hp': 55,   'dmg': 5,   'spd': 10,  'rng': 100, 'atk_spd': 2.0,  'size': 6,  'cost': 50, 'summons': 'skeleton'},
    'skeleton':      {'hp': 5,    'dmg': 5,   'spd': 25,  'rng': 25,  'atk_spd': 0.9,  'size': 5,  'cost': 0,  'is_summon': True},
    'wiz_builder':   {'hp': 25,   'dmg': 0,   'spd': 40,  'rng': 0,   'size': 5,        'cost': 38, 'is_builder': True, 'build_time': 11, 'b_type': 'library'},
    'elf_archer':    {'hp': 25,   'dmg': 25,  'spd': 50,  'rng': 150, 'atk_spd': 5.0,  'size': 5,  'cost': 50},
    'elf_rogue':     {'hp': 15,   'dmg': 15,  'spd': 75,  'rng': 20,  'atk_spd': 0.85, 'size': 5,  'cost': 50, 'burst_dmg': 100},
    'elf_builder':   {'hp': 25,   'dmg': 0,   'spd': 50,  'rng': 0,   'size': 5,        'cost': 32, 'is_builder': True, 'build_time': 9,  'b_type': 'stonecircle'},
    'pal_knight':    {'hp': 150,  'dmg': 25,  'spd': 25,  'rng': 26,  'atk_spd': 2.5,  'size': 8,  'cost': 60},
    'pal_cleric':    {'hp': 25,   'dmg': 5,   'spd': 40,  'rng': 95,  'atk_spd': 1.0,  'size': 6,  'cost': 25, 'heal': 14},
    'pal_builder':   {'hp': 25,   'dmg': 0,   'spd': 50,  'rng': 0,   'size': 5,        'cost': 40, 'is_builder': True, 'build_time': 14, 'b_type': 'farm'},
    'iron_foot':     {'hp': 180,  'dmg': 18,  'spd': 22,  'rng': 24,  'atk_spd': 1.8,  'size': 8,  'cost': 55},
    'iron_ballista': {'hp': 60,   'dmg': 40,  'spd': 15,  'rng': 160, 'atk_spd': 3.5,  'size': 7,  'cost': 70, 'aoe': 18},
    'iron_builder':  {'hp': 25,   'dmg': 0,   'spd': 35,  'rng': 0,   'size': 5,        'cost': 35, 'is_builder': True, 'build_time': 12, 'b_type': 'granary'},
    'shade_rogue':   {'hp': 30,   'dmg': 18,  'spd': 70,  'rng': 22,  'atk_spd': 0.9,  'size': 5,  'cost': 40, 'poison_on_hit': True},
    'phantom':       {'hp': 20,   'dmg': 35,  'spd': 80,  'rng': 18,  'atk_spd': 0.7,  'size': 5,  'cost': 55, 'burst_dmg': 90, 'poison_on_hit': True},
    'purp_builder':  {'hp': 25,   'dmg': 0,   'spd': 50,  'rng': 0,   'size': 5,        'cost': 32, 'is_builder': True, 'build_time': 10, 'b_type': 'thieves_den'},
    'storm_lancer':  {'hp': 90,   'dmg': 22,  'spd': 80,  'rng': 24,  'atk_spd': 1.4,  'size': 7,  'cost': 50, 'charge_dmg': True},
    'storm_shaman':  {'hp': 45,   'dmg': 8,   'spd': 55,  'rng': 110, 'atk_spd': 2.5,  'size': 6,  'cost': 45, 'chains': 2},
    'cyan_builder':  {'hp': 25,   'dmg': 0,   'spd': 55,  'rng': 0,   'size': 5,        'cost': 32, 'is_builder': True, 'build_time': 10, 'b_type': 'stable'},
    'bone_archer':   {'hp': 35,   'dmg': 20,  'spd': 30,  'rng': 130, 'atk_spd': 2.0,  'size': 6,  'cost': 45, 'raise_dead': True},
    'death_knight':  {'hp': 140,  'dmg': 28,  'spd': 30,  'rng': 26,  'atk_spd': 2.0,  'size': 8,  'cost': 65, 'aoe': 30},
    'bone_builder':  {'hp': 25,   'dmg': 0,   'spd': 35,  'rng': 0,   'size': 5,        'cost': 32, 'is_builder': True, 'build_time': 11, 'b_type': 'ossuary'},
    'frost_mage':    {'hp': 45,   'dmg': 12,  'spd': 18,  'rng': 120, 'atk_spd': 2.2,  'size': 6,  'cost': 45, 'frost_slow': True},
    'ice_golem':     {'hp': 280,  'dmg': 20,  'spd': 16,  'rng': 26,  'atk_spd': 2.5,  'size': 10, 'cost': 80, 'no_regen': True},
    'ice_builder':   {'hp': 25,   'dmg': 0,   'spd': 35,  'rng': 0,   'size': 5,        'cost': 35, 'is_builder': True, 'build_time': 12, 'b_type': 'frost_shrine'},
    'myconid':       {'hp': 30,   'dmg': 8,   'spd': 30,  'rng': 60,  'atk_spd': 1.5,  'size': 6,  'cost': 35, 'aoe': 55, 'is_bomber': True},
    'spore_shaman':  {'hp': 40,   'dmg': 6,   'spd': 22,  'rng': 100, 'atk_spd': 1.8,  'size': 6,  'cost': 45, 'aoe': 40},
    'olive_builder': {'hp': 25,   'dmg': 0,   'spd': 35,  'rng': 0,   'size': 5,        'cost': 28, 'is_builder': True, 'build_time': 10, 'b_type': 'mycelium'},
    'fire_war':      {'hp': 100,  'dmg': 20,  'spd': 38,  'rng': 22,  'atk_spd': 1.5,  'size': 7,  'cost': 50, 'burn_aura': True},
    'fire_priest':   {'hp': 50,   'dmg': 10,  'spd': 25,  'rng': 90,  'atk_spd': 2.0,  'size': 6,  'cost': 45, 'aoe': 50},
    'orange_builder':{'hp': 25,   'dmg': 0,   'spd': 38,  'rng': 0,   'size': 5,        'cost': 30, 'is_builder': True, 'build_time': 10, 'b_type': 'forge'},
    'bless_knight':  {'hp': 120,  'dmg': 22,  'spd': 30,  'rng': 26,  'atk_spd': 2.0,  'size': 7,  'cost': 55, 'heal_on_kill': True},
    'seraph':        {'hp': 35,   'dmg': 5,   'spd': 40,  'rng': 100, 'atk_spd': 1.5,  'size': 6,  'cost': 40, 'heal': 18},
    'gold_builder':  {'hp': 25,   'dmg': 0,   'spd': 40,  'rng': 0,   'size': 5,        'cost': 35, 'is_builder': True, 'build_time': 11, 'b_type': 'shrine'},
    'sea_raider':    {'hp': 80,   'dmg': 18,  'spd': 55,  'rng': 24,  'atk_spd': 1.4,  'size': 7,  'cost': 45, 'river_bonus': True},
    'tide_caller':   {'hp': 45,   'dmg': 8,   'spd': 40,  'rng': 110, 'atk_spd': 2.0,  'size': 6,  'cost': 45, 'aoe': 55},
    'teal_builder':  {'hp': 25,   'dmg': 0,   'spd': 45,  'rng': 0,   'size': 5,        'cost': 30, 'is_builder': True, 'build_time': 10, 'b_type': 'harbor'},
    'berserker':     {'hp': 80,   'dmg': 20,  'spd': 55,  'rng': 22,  'atk_spd': 1.2,  'size': 7,  'cost': 45, 'blood_rage': True},
    'blood_shaman':  {'hp': 40,   'dmg': 8,   'spd': 35,  'rng': 95,  'atk_spd': 1.8,  'size': 6,  'cost': 40},
    'crim_builder':  {'hp': 25,   'dmg': 0,   'spd': 40,  'rng': 0,   'size': 5,        'cost': 30, 'is_builder': True, 'build_time': 10, 'b_type': 'blood_altar'},
    'stone_golem':   {'hp': 400,  'dmg': 25,  'spd': 14,  'rng': 28,  'atk_spd': 3.5,  'size': 12, 'cost': 90, 'no_regen': True},
    'siege_golem':   {'hp': 200,  'dmg': 40,  'spd': 10,  'rng': 140, 'atk_spd': 5.0,  'size': 10, 'cost': 80, 'no_regen': True, 'aoe': 35},
    'slate_builder': {'hp': 25,   'dmg': 0,   'spd': 28,  'rng': 0,   'size': 5,        'cost': 40, 'is_builder': True, 'build_time': 14, 'b_type': 'foundry'},
    'dream_archer':  {'hp': 30,   'dmg': 15,  'spd': 45,  'rng': 130, 'atk_spd': 2.5,  'size': 5,  'cost': 45, 'confuses': True},
    'dream_knight':  {'hp': 90,   'dmg': 18,  'spd': 40,  'rng': 24,  'atk_spd': 1.8,  'size': 7,  'cost': 50},
    'rose_builder':  {'hp': 25,   'dmg': 0,   'spd': 40,  'rng': 0,   'size': 5,        'cost': 32, 'is_builder': True, 'build_time': 11, 'b_type': 'dream_spire'},
    'elem_fire':     {'hp': 900,  'dmg': 50,  'spd': 30,  'rng': 90,  'atk_spd': 1.4,  'size': 16, 'is_titan': True, 'aoe': 72,  'river_bonus': True},
    'elem_water':    {'hp': 900,  'dmg': 50,  'spd': 30,  'rng': 115, 'atk_spd': 1.8,  'size': 15, 'is_titan': True, 'aoe': 82, 'chains': 3, 'river_bonus': True},
    'elem_earth':    {'hp': 1100, 'dmg': 50,  'spd': 25,  'rng': 95,  'atk_spd': 2.8,  'size': 18, 'is_titan': True, 'aoe': 55,  'river_bonus': True},
    'elem_air':      {'hp': 700,  'dmg': 100, 'spd': 50,  'rng': 28,  'atk_spd': 0.9,  'size': 14, 'is_titan': True, 'river_bonus': True},
    'chaos_titan':   {'hp': 1000, 'dmg': 60,  'spd': 35,  'rng': 80,  'atk_spd': 1.5,  'size': 16, 'is_titan': True, 'aoe': 65, 'chains': 2, 'river_bonus': True},
}

SPAWN_POOLS = {
    'red':    ['hive_swarm', 'hive_swarm', 'hive_swarm', 'hive_soldier', 'hive_host'],
    'blue':   ['wiz_fire', 'wiz_storm', 'wiz_necro'],
    'green':  ['elf_archer', 'elf_archer', 'elf_rogue'],
    'yellow': ['pal_knight', 'pal_knight', 'pal_cleric'],
    'steel':  ['iron_foot', 'iron_foot', 'iron_ballista'],
    'purp':   ['shade_rogue', 'shade_rogue', 'phantom'],
    'cyan':   ['storm_lancer', 'storm_lancer', 'storm_shaman'],
    'bone':   ['bone_archer', 'bone_archer', 'death_knight'],
    'ice':    ['frost_mage', 'frost_mage', 'ice_golem'],
    'olive':  ['myconid', 'myconid', 'spore_shaman'],
    'orange': ['fire_war', 'fire_war', 'fire_priest'],
    'gold':   ['bless_knight', 'bless_knight', 'seraph'],
    'teal':   ['sea_raider', 'sea_raider', 'tide_caller'],
    'crim':   ['berserker', 'berserker', 'blood_shaman'],
    'slate':  ['stone_golem', 'siege_golem', 'stone_golem'],
    'rose':   ['dream_archer', 'dream_archer', 'dream_knight'],
}

FBLDG = {
    'red':    {'income': 'spore_cluster', 'defense': 'brood_nest',   'special': 'tumor',  'builder': 'hive_builder'},
    'blue':   {'income': 'library',       'defense': 'arcane_turret',                      'builder': 'wiz_builder'},
    'green':  {'income': 'stonecircle',   'defense': 'elf_forest',                          'builder': 'elf_builder'},
    'yellow': {'income': 'farm',          'defense': 'church',                              'builder': 'pal_builder'},
    'steel':  {'income': 'granary',       'defense': 'rampart',                             'builder': 'iron_builder'},
    'purp':   {'income': 'thieves_den',   'defense': 'shadow_trap',                         'builder': 'purp_builder'},
    'cyan':   {'income': 'stable',        'defense': 'storm_totem',                         'builder': 'cyan_builder'},
    'bone':   {'income': 'ossuary',       'defense': 'death_shrine',                        'builder': 'bone_builder'},
    'ice':    {'income': 'frost_shrine',  'defense': 'ice_wall',                            'builder': 'ice_builder'},
    'olive':  {'income': 'mycelium',      'defense': 'spore_tower',                         'builder': 'olive_builder'},
    'orange': {'income': 'forge',         'defense': 'fire_pit',                            'builder': 'orange_builder'},
    'gold':   {'income': 'shrine',        'defense': 'beacon',                              'builder': 'gold_builder'},
    'teal':   {'income': 'harbor',        'defense': 'tide_shrine',                         'builder': 'teal_builder'},
    'crim':   {'income': 'blood_altar',   'defense': 'rage_totem',                          'builder': 'crim_builder'},
    'slate':  {'income': 'foundry',       'defense': 'rampart',                             'builder': 'slate_builder'},
    'rose':   {'income': 'dream_spire',   'defense': 'veil_shrine',                         'builder': 'rose_builder'},
}

FTITAN = {
    'red': 'elem_fire', 'blue': 'elem_water', 'green': 'elem_earth', 'yellow': 'elem_air',
    'steel': 'elem_earth', 'purp': 'chaos_titan', 'cyan': 'elem_air', 'bone': 'chaos_titan',
    'ice': 'elem_water', 'olive': 'elem_earth', 'orange': 'elem_fire', 'gold': 'elem_air',
    'teal': 'elem_water', 'crim': 'elem_fire', 'slate': 'elem_earth', 'rose': 'chaos_titan',
}

# Region grid: 5 columns × 4 rows = 20 named regions
REGION_NAMES = [
    'Ironmoor',   'Crystalfen', 'Ashvale',    'Sundrift',   'Stonehaven',
    'Duskwood',   'Saltmarsh',  'Thornfield', 'Riverkeep',  'Frostholm',
    'Grimgate',   'Embervast',  'Shadowmere', 'Goldcrest',  'Bleakwatch',
    'Deepwatch',  'Cinderfall', 'Mudholm',    'Highwater',  'Ruinpass',
]
REGION_COLS = 5
REGION_ROWS = 4


def pick_factions():
    keys = list(ALL_FACTIONS.keys())
    random.shuffle(keys)
    chosen = keys[:6]
    factions = {}
    for i, k in enumerate(chosen):
        factions[k] = {**ALL_FACTIONS[k], 'cx': STARTS[i][0], 'cy': STARTS[i][1]}
    return chosen, factions
