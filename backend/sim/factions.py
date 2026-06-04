import os
import random

MAP_W = 1200
MAP_H = 820

TITAN_TIME      = 1200
TOWER_EXPIRE    = 600
RESTART_DELAY   = 120
PASSIVE_GOLD    = 10
BUILD_GOLD      = 2.5
SWARM_THRESHOLD = 9
MAX_INC_BLDG    = 3
MAX_DEF_BLDG    = 2
MAX_SPECIAL     = 2
MAX_UNITS_PER_FACTION = 38
PANEL_GRACE     = 35

# Per-faction unit cap overrides — factions not listed use MAX_UNITS_PER_FACTION
FACTION_UNIT_CAPS = {
    'dagon':  80,   # swarm faction needs a much higher cap
    'red':    60,   # hive swarm also benefits
    'olive':  60,   # mushling swarm
}

# Per-faction base spawn interval in seconds (Castle.update uses this)
FACTION_SPAWN_INTERVAL = {
    'dagon':  0.5,   # cultists are cheap; need fast production
    'red':    0.65,
}

TICK_INTERVAL   = 0.033
GAME_SPEED      = 1.0

DISASTER_INTERVAL = float(os.environ.get('DISASTER_INTERVAL', 300))

STARTS = [[160, 160], [600, 130], [1040, 160], [160, 660], [600, 690], [1040, 660]]

ALL_FACTIONS = {
    'red':    {'id': 'red',    'name': 'HEMOPHAGE HIVE',        'color': '#D44040', 'lo': '#420A0A', 'hi': '#FF5555'},
    'blue':   {'id': 'blue',   'name': 'ARCANE ACADEMY',        'color': '#5090E8', 'lo': '#0E2255', 'hi': '#88BBFF'},
    'green':  {'id': 'green',  'name': 'SYLVAN STEWARDS',       'color': '#44CC55', 'lo': '#0E3818', 'hi': '#88FF99'},
    'yellow': {'id': 'yellow', 'name': 'LUX LEGIONIS',          'color': '#E8C030', 'lo': '#4A3C08', 'hi': '#FFE060'},
    'steel':  {'id': 'steel',  'name': 'GNOMISH GEARSMITHS',    'color': '#9AAABB', 'lo': '#2A3040', 'hi': '#DDEEFF'},
    'bone':   {'id': 'bone',   'name': 'CRYPTLORD CABAL',       'color': '#C8C080', 'lo': '#282410', 'hi': '#FFFFC0'},
    'olive':  {'id': 'olive',  'name': 'MYCELIUM MULTITUDE',    'color': '#88AA22', 'lo': '#1A2008', 'hi': '#CCEE44'},
    'gold':   {'id': 'gold',   'name': 'CELESTIAL CHOIR',       'color': '#FFD700', 'lo': '#3A3000', 'hi': '#FFEEAA'},
    'crim':   {'id': 'crim',   'name': 'SANGUINE SUPPLICANTS',  'color': '#CC2222', 'lo': '#300808', 'hi': '#FF6666'},
    'slate':  {'id': 'slate',  'name': 'FABRICATOR FORGES',     'color': '#7788AA', 'lo': '#1A2030', 'hi': '#AABBCC'},
    'brown':  {'id': 'brown',  'name': 'BULWARK BASTION',       'color': '#AA8855', 'lo': '#3A2810', 'hi': '#DDBB88'},
    'dagon':  {'id': 'dagon',  'name': 'DREAMERS OF DAGON',     'color': '#6644AA', 'lo': '#1A0830', 'hi': '#9966DD'},
    'pink':   {'id': 'pink',   'name': 'HOSTILE HOSPICE',       'color': '#DD55AA', 'lo': '#3A0820', 'hi': '#FF88CC'},
    'mann':   {'id': 'mann',   'name': 'EMPIRE OF MAN',         'color': '#CC9944', 'lo': '#3A2808', 'hi': '#FFCC66'},
    'goblin': {'id': 'goblin', 'name': 'GOBLIN GANG',           'color': '#44AA44', 'lo': '#0A2008', 'hi': '#88DD88'},
    'apoc':   {'id': 'apoc',   'name': 'HORSEMEN OF THE APOCALYPSE',  'color': '#AA2244', 'lo': '#2A0810', 'hi': '#FF4466'},
}

UTYPES = {
    # ── HEMOPHAGE HIVE (red) ─────────────────────────────────────────────────────
    'hive_swarm':    {'hp': 10,   'dmg': 1,   'spd': 75,  'rng': 18,  'atk_spd': 0.25, 'size': 5,  'cost': 2},
    'hive_soldier':  {'hp': 75,   'dmg': 15,  'spd': 50,  'rng': 22,  'atk_spd': 1.0,  'size': 7,  'cost': 30},
    'hive_host':     {'hp': 90,   'dmg': 0,   'spd': 10,  'rng': 115, 'atk_spd': 10.0, 'size': 9,  'cost': 50, 'spawns': 'hive_mite'},
    'hive_mite':     {'hp': 5,    'dmg': 50,  'spd': 30,  'rng': 14,  'atk_spd': 1.0,  'size': 3,  'cost': 0,  'is_bomber': True, 'aoe': 38},
    'hive_builder':  {'hp': 25,   'dmg': 0,   'spd': 40,  'rng': 0,   'size': 5,        'cost': 28, 'is_builder': True, 'build_time': 9,  'b_type': 'biomass_tumor'},
    'brood_bug':     {'hp': 22,   'dmg': 6,   'spd': 58,  'rng': 18,  'atk_spd': 0.6,  'size': 4,  'cost': 0},
    # ── ARCANE ACADEMY (blue) ────────────────────────────────────────────────────
    'fire_mage':    {'hp': 25, 'dmg': 25, 'spd': 14, 'rng': 110, 'atk_spd': 2.0, 'size': 6, 'cost': 55, 'aoe': 35, 'fire_dot': True},
    'water_mage':   {'hp': 25, 'dmg': 30, 'spd': 14, 'rng': 115, 'atk_spd': 2.5, 'size': 6, 'cost': 55, 'frost_slow': True},
    'earth_mage':   {'hp': 50, 'dmg': 50, 'spd': 14, 'rng': 105, 'atk_spd': 4, 'size': 6, 'cost': 60},
    'air_mage':     {'hp': 25, 'dmg': 20, 'spd': 14, 'rng': 120, 'atk_spd': 2.0, 'size': 6, 'cost': 60, 'chains': 3},
    'acad_builder': {'hp': 25, 'dmg': 0,  'spd': 35, 'rng': 0,   'size': 5, 'cost': 38, 'is_builder': True, 'build_time': 11, 'b_type': 'library'},
    # ── SYLVAN STEWARDS (green) ──────────────────────────────────────────────────
    'elf_archer':   {'hp': 30,  'dmg': 50, 'spd': 50, 'rng': 150, 'atk_spd': 4, 'size': 5,  'cost': 50},
    'elf_rogue':    {'hp': 20,  'dmg': 18, 'spd': 75, 'rng': 22,  'atk_spd': 0.9, 'size': 5,  'cost': 55, 'burst_dmg': 110},
    'treant':       {'hp': 380, 'dmg': 35, 'spd': 14, 'rng': 28,  'atk_spd': 3.0, 'size': 13, 'cost': 80},
    'elf_builder':  {'hp': 25,  'dmg': 0,  'spd': 50, 'rng': 0,   'size': 5,       'cost': 32, 'is_builder': True, 'build_time': 9, 'b_type': 'forest'},
    # ── LUX LEGIONIS (yellow) ────────────────────────────────────────────────────
    'pal_knight':   {'hp': 180, 'dmg': 28, 'spd': 22, 'rng': 26, 'atk_spd': 2.8, 'size': 8, 'cost': 70, 'armor': 0.30},
    'pal_cleric':   {'hp': 30,  'dmg': 6,  'spd': 40, 'rng': 95, 'atk_spd': 1.0, 'size': 6, 'cost': 30, 'heal': 16},
    'squire':       {'hp': 80,  'dmg': 14, 'spd': 35, 'rng': 24, 'atk_spd': 1.6, 'size': 6, 'cost': 40},
    'pal_builder':  {'hp': 25,  'dmg': 0,  'spd': 50, 'rng': 0,  'size': 5,       'cost': 40, 'is_builder': True, 'build_time': 12, 'b_type': 'blacksmithy'},
    # ── GNOMISH GEARSMITHS (steel) ───────────────────────────────────────────────
    'gnome_sapper':    {'hp': 50,  'dmg': 20, 'spd': 30, 'rng': 140, 'atk_spd': 3.0, 'size': 6,  'cost': 60,  'aoe': 45, 'is_sapper': True},
    'gnome_craftsman': {'hp': 70,  'dmg': 14, 'spd': 28, 'rng': 26,  'atk_spd': 1.8, 'size': 6,  'cost': 55,  'is_craftsman': True},
    'gnome_titan':     {'hp': 500, 'dmg': 45, 'spd': 16, 'rng': 120, 'atk_spd': 2.5, 'size': 14, 'cost': 120, 'armor': 0.25, 'aoe': 35, 'no_regen': True},
    'clockwork':       {'hp': 25,  'dmg': 10, 'spd': 45, 'rng': 22,  'atk_spd': 1.0, 'size': 5,  'cost': 0,   'is_summon': True, 'is_clockwork': True},
    'steel_builder':   {'hp': 25,  'dmg': 0,  'spd': 32, 'rng': 0,   'size': 5,       'cost': 35, 'is_builder': True, 'build_time': 12, 'b_type': 'gnomish_workshop'},
    # ── CRYPTLORD CABAL (bone) ───────────────────────────────────────────────────
    'bone_death_knight': {'hp': 100, 'dmg': 30, 'spd': 22, 'rng': 26,  'atk_spd': 2.0, 'size': 9, 'cost': 75,  'summons': 'zombie', 'raise_dead': True},
    'lich':              {'hp': 70,  'dmg': 20, 'spd': 18, 'rng': 130, 'atk_spd': 2.5, 'size': 7, 'cost': 80,  'summons': 'crypt_skeleton'},
    'dominus_mortus':    {'hp': 50,  'dmg': 0,  'spd': 14, 'rng': 0,   'atk_spd': 1.0, 'size': 7, 'cost': 200, 'is_dominus': True},
    'zombie':            {'hp': 5,  'dmg': 2, 'spd': 15, 'rng': 22,  'atk_spd': 1.4, 'size': 6, 'cost': 0,   'is_summon': True, 'raise_dead': True},
    'crypt_skeleton':    {'hp': 5,  'dmg': 2, 'spd': 15, 'rng': 20, 'atk_spd': 2.2, 'size': 5, 'cost': 0,   'is_summon': True},
    'crypt_archer':      {'hp': 5,  'dmg': 5, 'spd': 15, 'rng': 100, 'atk_spd': 2.0, 'size': 5, 'cost': 0,   'is_crypt_unit': True},
    'bone_builder':      {'hp': 25,  'dmg': 0,  'spd': 35, 'rng': 0,   'size': 5,       'cost': 32, 'is_builder': True, 'build_time': 11, 'b_type': 'graveyard'},
    # ── MYCELIUM MULTITUDE (olive) ───────────────────────────────────────────────
    'mushling':          {'hp': 50,  'dmg': 4,  'spd': 40, 'rng': 18,  'atk_spd': 0.7, 'size': 5, 'cost': 10},
    'sporeburster':      {'hp': 120, 'dmg': 8,  'spd': 16, 'rng': 22,  'atk_spd': 1.8, 'size': 9, 'cost': 50, 'aoe': 45},
    'sporomancer':       {'hp': 40,  'dmg': 5,  'spd': 28, 'rng': 110, 'atk_spd': 3.0, 'size': 6, 'cost': 60, 'is_sporomancer': True},
    'olive_builder':     {'hp': 25,  'dmg': 0,  'spd': 35, 'rng': 0,   'size': 5,       'cost': 28, 'is_builder': True, 'build_time': 10, 'b_type': 'fungal_patch'},
    # ── CELESTIAL CHOIR (gold) ───────────────────────────────────────────────────
    'axe_guitar':      {'hp': 60,  'dmg': 18, 'spd': 35, 'rng': 24,  'atk_spd': 1.4, 'size': 6, 'cost': 50, 'choir_aura': 'dmg'},
    'tuba_cannon':     {'hp': 55,  'dmg': 12, 'spd': 18, 'rng': 130, 'atk_spd': 4.0, 'size': 7, 'cost': 60, 'choir_aura': 'hp'},
    'war_drummer':     {'hp': 40,  'dmg': 8,  'spd': 45, 'rng': 22,  'atk_spd': 1.0, 'size': 5, 'cost': 45, 'aoe': 30, 'choir_aura': 'spd'},
    'conductor':       {'hp': 35,  'dmg': 5,  'spd': 30, 'rng': 90,  'atk_spd': 2.0, 'size': 6, 'cost': 80, 'choir_aura': 'atk_spd'},
    'pianist':         {'hp': 45,  'dmg': 10, 'spd': 22, 'rng': 100, 'atk_spd': 3.0, 'size': 6, 'cost': 65, 'aoe': 55, 'choir_aura': 'heal', 'heal': 8},
    'blowdart_flute':  {'hp': 30,  'dmg': 12, 'spd': 55, 'rng': 120, 'atk_spd': 2.2, 'size': 5, 'cost': 55, 'choir_aura': 'aoe'},
    'soundboard_tech': {'hp': 40,  'dmg': 8,  'spd': 32, 'rng': 80,  'atk_spd': 2.0, 'size': 6, 'cost': 55, 'choir_aura': 'rng'},
    'choir_fan':       {'hp': 15,  'dmg': 5,  'spd': 50, 'rng': 18,  'atk_spd': 0.6, 'size': 4, 'cost': 0,  'is_summon': True},
    'gold_builder':    {'hp': 25,  'dmg': 0,  'spd': 40, 'rng': 0,   'size': 5,       'cost': 35, 'is_builder': True, 'build_time': 11, 'b_type': 'amphitheater'},
    # ── SANGUINE SUPPLICANTS (crim) ──────────────────────────────────────────────
    'blood_knight':    {'hp': 200, 'dmg': 10, 'spd': 30, 'rng': 26,  'atk_spd': 1.8, 'size': 9, 'cost': 70, 'is_blood_knight': True},
    'blood_mage':      {'hp': 50,  'dmg': 10, 'spd': 25, 'rng': 110, 'atk_spd': 2.2, 'size': 6, 'cost': 60, 'is_blood_mage': True},
    'crim_builder':    {'hp': 25,  'dmg': 0,  'spd': 40, 'rng': 0,   'size': 5,       'cost': 30, 'is_builder': True, 'build_time': 10, 'b_type': 'blood_fountain'},
    # ── FABRICATOR FORGES (slate) ────────────────────────────────────────────────
    'gnome_engineer':  {'hp': 45,  'dmg': 0,  'spd': 36, 'rng': 0,   'size': 5,  'cost': 55, 'is_engineer': True},
    'forge_golem':     {'hp': 450, 'dmg': 22, 'spd': 14, 'rng': 28,  'atk_spd': 3.0, 'size': 13, 'cost': 85, 'no_regen': True, 'armor': 0.20},
    'forge_tank':      {'hp': 100, 'dmg': 45, 'spd': 16, 'rng': 150, 'atk_spd': 4.0, 'size': 8,  'cost': 100, 'no_regen': True, 'aoe': 22},
    'slate_builder':   {'hp': 25,  'dmg': 0,  'spd': 28, 'rng': 0,   'size': 5,       'cost': 40, 'is_builder': True, 'build_time': 14, 'b_type': 'mines'},
    # ── BULWARK BASTION (brown) ──────────────────────────────────────────────────
    'bastion_builder': {'hp': 35,  'dmg': 4,  'spd': 32, 'rng': 24,  'atk_spd': 2.0, 'size': 5, 'cost': 35, 'is_bastion_builder': True},
    'bastion_archer':  {'hp': 40,  'dmg': 30, 'spd': 38, 'rng': 155, 'atk_spd': 4.0, 'size': 5, 'cost': 55},
    'bastion_mortar':  {'hp': 55,  'dmg': 28, 'spd': 18, 'rng': 200, 'atk_spd': 5.0, 'size': 7, 'cost': 70, 'aoe': 40},
    # ── DREAMERS OF DAGON (dagon) ────────────────────────────────────────────────
    'cultist':         {'hp': 10,  'dmg': 5,  'spd': 55, 'rng': 18,  'atk_spd': 0.7, 'size': 4, 'cost': 5},
    'cult_leader':     {'hp': 30,  'dmg': 8,  'spd': 35, 'rng': 80,  'atk_spd': 2.0, 'size': 6, 'cost': 80, 'is_cult_leader': True},
    'elder_god':       {'hp': 500, 'dmg': 60, 'spd': 22, 'rng': 90,  'atk_spd': 1.8, 'size': 14,'cost': 300, 'aoe': 60, 'is_elder_god': True},
    'dagon_builder':   {'hp': 25,  'dmg': 0,  'spd': 40, 'rng': 0,   'size': 5,       'cost': 30, 'is_builder': True, 'build_time': 10, 'b_type': 'altar_of_madness'},
    # ── HOSTILE HOSPICE (pink) ───────────────────────────────────────────────────
    'test_subject':    {'hp': 60,  'dmg': 15, 'spd': 35, 'rng': 22,  'atk_spd': 1.5, 'size': 6, 'cost': 40, 'is_test_subject': True},
    'plague_doctor':   {'hp': 35,  'dmg': 8,  'spd': 32, 'rng': 110, 'atk_spd': 2.5, 'size': 6, 'cost': 55, 'plague_dot': True},
    'pink_builder':    {'hp': 25,  'dmg': 0,  'spd': 38, 'rng': 0,   'size': 5,       'cost': 30, 'is_builder': True, 'build_time': 10, 'b_type': 'lab'},
    # ── EMPIRE OF MAN (mann) ─────────────────────────────────────────────────────
    'hoplite':         {'hp': 130, 'dmg': 18, 'spd': 28, 'rng': 26,  'atk_spd': 2.0, 'size': 7, 'cost': 55, 'armor': 0.0, 'is_hoplite': True},
    'mann_archer':     {'hp': 45,  'dmg': 22, 'spd': 42, 'rng': 140, 'atk_spd': 3.5, 'size': 5, 'cost': 50, 'is_mann_archer': True},
    'bard':            {'hp': 35,  'dmg': 6,  'spd': 38, 'rng': 90,  'atk_spd': 2.5, 'size': 5, 'cost': 55, 'is_bard': True},
    'mann_builder':    {'hp': 25,  'dmg': 0,  'spd': 40, 'rng': 0,   'size': 5,       'cost': 35, 'is_builder': True, 'build_time': 10, 'b_type': 'mann_farm'},
    # ── GOBLIN GANG (goblin) ─────────────────────────────────────────────────────
    'wolf':            {'hp': 70,  'dmg': 15, 'spd': 75, 'rng': 22,  'atk_spd': 1.0, 'size': 6, 'cost': 35},
    'wolf_rider':      {'hp': 75,  'dmg': 18, 'spd': 80, 'rng': 24,  'atk_spd': 1.2, 'size': 7, 'cost': 50, 'death_spawn': 'goblin'},
    'mangudai':        {'hp': 50,  'dmg': 20, 'spd': 75, 'rng': 110, 'atk_spd': 2.5, 'size': 6, 'cost': 55, 'death_spawn': 'goblin_archer'},
    'goblin':          {'hp': 12,  'dmg': 6,  'spd': 55, 'rng': 18,  'atk_spd': 0.6, 'size': 4, 'cost': 0,  'is_summon': True, 'goblin_debuff': True},
    'goblin_archer':   {'hp': 10,  'dmg': 8,  'spd': 60, 'rng': 100, 'atk_spd': 1.8, 'size': 4, 'cost': 0,  'is_summon': True},
    'goblin_builder':  {'hp': 25,  'dmg': 0,  'spd': 50, 'rng': 0,   'size': 5,       'cost': 28, 'is_builder': True, 'build_time': 9, 'b_type': 'fighting_pit'},
    # ── HORSEMEN OF THE APOCALYPSE (apoc) ────────────────────────────────────────
    'pestilence':      {'hp': 300, 'dmg': 20, 'spd': 30, 'rng': 28,  'atk_spd': 1.0, 'size': 8,  'cost': 150, 'fire_dot': True, 'is_horseman': True, 'horseman_idx': 0},
    'war_horseman':    {'hp': 350, 'dmg': 50, 'spd': 28, 'rng': 28,  'atk_spd': 1.0, 'size': 10, 'cost': 250, 'is_horseman': True, 'horseman_idx': 1},
    'famine':          {'hp': 400, 'dmg': 25, 'spd': 25, 'rng': 28,  'atk_spd': 2.0, 'size': 9,  'cost': 350, 'is_horseman': True, 'horseman_idx': 2, 'is_famine': True},
    'death_horseman':  {'hp': 450, 'dmg': 100,'spd': 18, 'rng': 30,  'atk_spd': 2.0, 'size': 11, 'cost': 500, 'is_horseman': True, 'horseman_idx': 3},
    'apoc_builder':    {'hp': 25,  'dmg': 0,  'spd': 35, 'rng': 0,   'size': 5,       'cost': 30, 'is_builder': True, 'build_time': 12, 'b_type': 'cairn'},
    # ── FROGS (neutral disaster units) ───────────────────────────────────────────
    # Hostile to all factions; no_regen so they don't recover; short-lived fighters.
    'frog':            {'hp': 20,  'dmg': 5,  'spd': 52, 'rng': 18,  'atk_spd': 0.8, 'size': 4, 'cost': 0,  'is_summon': True},
    # ── TITANS ───────────────────────────────────────────────────────────────────
    'elem_fire':       {'hp': 5000,  'dmg': 50,  'spd': 30, 'rng': 90,  'atk_spd': 1.4, 'size': 16, 'is_titan': True, 'aoe': 72,  'river_bonus': True},
    'elem_water':      {'hp': 5000,  'dmg': 50,  'spd': 30, 'rng': 115, 'atk_spd': 1.8, 'size': 15, 'is_titan': True, 'aoe': 82,  'chains': 3, 'river_bonus': True},
    'elem_earth':      {'hp': 5000, 'dmg': 50,  'spd': 25, 'rng': 95,  'atk_spd': 2.8, 'size': 18, 'is_titan': True, 'aoe': 55,  'river_bonus': True},
    'elem_air':        {'hp': 5000,  'dmg': 100, 'spd': 50, 'rng': 28,  'atk_spd': 0.9, 'size': 14, 'is_titan': True, 'river_bonus': True},
    'chaos_titan':     {'hp': 5000, 'dmg': 60,  'spd': 35, 'rng': 80,  'atk_spd': 1.5, 'size': 16, 'is_titan': True, 'aoe': 65,  'chains': 2, 'river_bonus': True},
    'death_titan':     {'hp': 5000, 'dmg': 55,  'spd': 20, 'rng': 32,  'atk_spd': 1.6, 'size': 18, 'is_titan': True, 'aoe': 50,  'river_bonus': True, 'raise_dead': True},
}

SPAWN_POOLS = {
    'red':    ['hive_swarm', 'hive_swarm', 'hive_swarm', 'hive_soldier', 'hive_host'],
    'blue':   ['fire_mage', 'water_mage', 'earth_mage', 'air_mage'],
    'green':  ['elf_archer', 'elf_archer', 'elf_rogue', 'treant'],
    'yellow': ['pal_knight', 'pal_knight', 'squire', 'squire', 'pal_cleric'],
    'steel':  ['gnome_sapper', 'gnome_sapper', 'gnome_craftsman', 'gnome_titan'],
    'bone':   ['bone_death_knight', 'bone_death_knight', 'lich'],
    'olive':  ['mushling', 'mushling', 'mushling', 'sporeburster', 'sporomancer'],
    'gold':   ['axe_guitar', 'tuba_cannon', 'war_drummer', 'conductor', 'pianist', 'blowdart_flute', 'soundboard_tech'],
    'crim':   ['blood_knight', 'blood_knight', 'blood_mage'],
    'slate':  ['gnome_engineer', 'forge_golem', 'forge_golem', 'forge_tank'],
    'brown':  ['bastion_archer', 'bastion_archer', 'bastion_mortar'],
    'dagon':  ['cultist', 'cultist', 'cultist', 'cultist', 'cult_leader'],
    'pink':   ['test_subject', 'test_subject', 'plague_doctor'],
    'mann':   ['hoplite', 'hoplite', 'mann_archer', 'mann_archer', 'bard'],
    'goblin': ['wolf', 'wolf', 'wolf_rider', 'mangudai'],
    'apoc':   ['pestilence'],   # Castle._try_spawn enforces sequential unlocking
}

FBLDG = {
    'red':    {'income': 'biomass_tumor',     'defense': 'def_hive',         'special': 'biomass_tumor', 'builder': 'hive_builder'},
    'blue':   {'income': 'library',           'defense': 'arcane_turret',                                 'builder': 'acad_builder'},
    'green':  {'income': 'forest',            'defense': 'bramble_patch',                                 'builder': 'elf_builder'},
    'yellow': {'income': 'blacksmithy',       'defense': 'church',                                        'builder': 'pal_builder'},
    'steel':  {'income': 'gnomish_workshop',  'defense': 'minefield',                                     'builder': 'steel_builder'},
    'bone':   {'income': 'graveyard',         'defense': 'crypt',                                         'builder': 'bone_builder'},
    'olive':  {'income': 'fungal_patch',      'defense': 'sporolith',                                     'builder': 'olive_builder'},
    'gold':   {'income': 'amphitheater',      'defense': 'community_center',                              'builder': 'gold_builder'},
    'crim':   {'income': 'blood_fountain',    'defense': 'bloodstone',                                    'builder': 'crim_builder'},
    'slate':  {'income': 'mines',             'defense': 'flamethrower',                                  'builder': 'slate_builder'},
    'brown':  {'income': 'quarry',            'defense': 'bastila',           'special': 'bwall',         'builder': 'bastion_builder'},
    'dagon':  {'income': 'altar_of_madness',  'defense': 'void_rift',                                     'builder': 'dagon_builder'},
    'pink':   {'income': 'lab',               'defense': 'toxic_smokestack',                              'builder': 'pink_builder'},
    'mann':   {'income': 'mann_farm',         'defense': 'archer_tower',                                  'builder': 'mann_builder'},
    'goblin': {'income': 'fighting_pit',      'defense': 'pitfall_trap',                                  'builder': 'goblin_builder'},
    'apoc':   {'income': 'cairn',             'defense': 'marble_monument',   'special': 'cairn',         'builder': 'apoc_builder'},
}

FTITAN = {
    'red':    'elem_fire',   'blue':   'elem_water',  'green':  'elem_earth',
    'yellow': 'elem_air',    'steel':  'elem_earth',  'bone':   'death_titan',
    'olive':  'elem_earth',  'gold':   'elem_air',    'crim':   'elem_fire',
    'slate':  'elem_earth',  'brown':  'elem_earth',  'dagon':  'chaos_titan',
    'pink':   'chaos_titan', 'mann':   'elem_earth',  'goblin': 'chaos_titan',
    'apoc':   'chaos_titan',
}

REGION_NAMES = [
    'Ironmoor',    'Crystalfen',     'Ashvale',
    'Thornfield',  'The Heartlands', 'Shadowmere',
    'Grimgate',    'Saltmarsh',      'Frostholm',
]
REGION_COLS = 3
REGION_ROWS = 3


def pick_factions():
    keys = list(ALL_FACTIONS.keys())
    random.shuffle(keys)
    chosen = keys[:6]
    factions = {}
    for i, k in enumerate(chosen):
        factions[k] = {**ALL_FACTIONS[k], 'cx': STARTS[i][0], 'cy': STARTS[i][1]}
    return chosen, factions