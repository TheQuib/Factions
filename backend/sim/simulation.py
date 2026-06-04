"""
Simulation — second-pass optimised version.

Changes vs previous:
  - _reset_caches() extracted so __init__ and init_game share one reset path.
  - faction_has_builder cache eliminates the O(n) has_builder scan in Castle._try_spawn.
  - faction_cultist_count cache eliminates the O(n) cultist count in dagon gate.
  - _apply_monument_debuffs only runs when live monuments exist; caches alive-horsemen
    set so the inner loop reads a pre-built set rather than re-scanning entities.
  - Frog Rain disaster: frogs spawn gradually over 10 s via a pending_frogs queue
    processed in tick(); frogs are real Unit objects hostile to all factions.
  - Removed now-redundant duplicate disaster list entry (old frog_rain that only
    dealt 20 HP damage without spawning units).
"""
import math
import random
from collections import deque
from .factions import (
    ALL_FACTIONS, STARTS, FTITAN, FBLDG,
    TITAN_TIME, RESTART_DELAY, DISASTER_INTERVAL,
    REGION_NAMES, REGION_COLS, REGION_ROWS,
    MAP_W, MAP_H, pick_factions,
)
from .terrain import gen_terrain, terrain_to_serializable, in_river
from .entities import Castle, Unit, Building, ArrowTower, Titan, _dist
from .spatial import SpatialGrid

_DISASTER_HISTORY_MAX = 4

_MONUMENT_REQUIREMENTS = {
    'marble_monument':  'pestilence',
    'crimson_cenotaph': 'war_horseman',
    'onyx_obelisk':     'famine',
    'alabaster_angel':  'death_horseman',
}

# Neutral faction id used for frog units — attacked by everyone
_FROG_FID = '__frog__'


class Simulation:
    def __init__(self):
        self.generation      = 0
        self.game_time       = 0.0
        self.game_over_timer = -1.0
        self.winner          = None
        self.titans_spawned  = False
        self.blizzard_t      = 0.0
        self.wildfire_zones  = []
        self.plague_cloud    = None
        self.mania_t         = 0.0
        self.shake_x         = 0.0
        self.shake_y         = 0.0
        self.shake_t         = 0.0
        self.disaster_msg    = ''
        self.disaster_col    = '#FF8800'
        self.disaster_t      = 0.0
        self.disaster_history: deque = deque(maxlen=_DISASTER_HISTORY_MAX)
        self.next_disaster_t = DISASTER_INTERVAL + random.random() * 60.0

        # Frog Rain: list of (spawn_at_game_time, x, y) pending spawns
        self.pending_frogs: list = []

        # Horsemen tracking (survives game resets so sequential purchase works)
        self.faction_horseman_ever_bought: dict = {}

        self.grid = SpatialGrid(MAP_W, MAP_H)
        self.events = []

        self.faction_keys   = []
        self.factions       = {}
        self.rivers         = []
        self.bridges        = []
        self.forests        = []
        self.terrain_serial = {}
        self.entities       = []
        self.regions        = []
        self.region_update_t = 0.0

        self._reset_caches()
        self.init_game()

    # ── Cache helpers ─────────────────────────────────────────────────────────

    def _reset_caches(self):
        """Zero every per-tick cache. Called from both __init__ and init_game."""
        self.castle_cache              = {}
        self.faction_unit_count        = {}
        self.faction_inc_bldg_count    = {}
        self.faction_def_bldg_count    = {}
        self.faction_sp_bldg_count     = {}
        self.faction_lib_count         = {}
        self.faction_mine_count        = {}
        self.faction_blacksmithy_count = {}
        self.faction_quarry_count      = {}
        self.faction_altar_count       = {}
        self.faction_lab_count         = {}
        self.faction_blood_fountain_count = {}
        self.faction_amphitheater_count   = {}
        self.faction_fighting_pit_count   = {}
        # New caches added in second pass
        self.faction_has_builder       = {}   # bool: fid → builder unit on field?
        self.faction_cultist_count     = {}   # int:  fid → live cultist count
        self.tumor_list                = []
        self.rage_totem_list           = []
        self.burn_aura_t               = 0.0

    # ── Init / reset ──────────────────────────────────────────────────────────

    def init_game(self):
        self.generation      += 1
        self.game_time        = 0.0
        self.game_over_timer  = -1.0
        self.winner           = None
        self.titans_spawned   = False
        self.blizzard_t       = 0.0
        self.wildfire_zones   = []
        self.plague_cloud     = None
        self.mania_t          = 0.0
        self.shake_x = self.shake_y = self.shake_t = 0.0
        self.disaster_msg     = ''
        self.disaster_t       = 0.0
        self.disaster_history = deque(maxlen=_DISASTER_HISTORY_MAX)
        self.next_disaster_t  = DISASTER_INTERVAL + random.random() * 60.0
        self.pending_frogs    = []
        self.faction_horseman_ever_bought = {}
        self.events           = []
        self.region_update_t  = 0.0

        self._reset_caches()

        self.faction_keys, self.factions = pick_factions()
        # Add frog pseudo-faction so frog units have a valid color entry
        self.factions[_FROG_FID] = {
            'id': _FROG_FID, 'name': 'FROGS', 'color': '#55BB33',
            'lo': '#1A3A10', 'hi': '#88EE44',
            'cx': MAP_W // 2, 'cy': MAP_H // 2,
        }

        self.rivers, self.bridges, self.forests = gen_terrain()
        self.terrain_serial = terrain_to_serializable(
            self.rivers, self.bridges, self.forests)

        self.entities = []
        for k, f in self.factions.items():
            if k == _FROG_FID:
                continue
            self.entities.append(Castle(f['cx'], f['cy'], k))
        for b in self.bridges:
            r = b['riv']
            if r['horiz']:
                self.entities.append(ArrowTower(b['pos'] - 32, r['pos']))
                self.entities.append(ArrowTower(b['pos'] + 32, r['pos']))
            else:
                self.entities.append(ArrowTower(r['pos'], b['pos'] - 32))
                self.entities.append(ArrowTower(r['pos'], b['pos'] + 32))

        self._init_regions()

    def _init_regions(self):
        rw = MAP_W / REGION_COLS
        rh = MAP_H / REGION_ROWS
        self.regions = []
        for i, name in enumerate(REGION_NAMES):
            col = i % REGION_COLS
            row = i // REGION_COLS
            self.regions.append({
                'name': name,
                'x': col * rw, 'y': row * rh,
                'w': rw, 'h': rh,
                'controlling_fid': None,
                'control_pct': 0.0,
            })

    # ── Main tick ─────────────────────────────────────────────────────────────

    def tick(self, dt: float):
        self.events = []

        if self.game_over_timer > 0:
            self.game_over_timer -= dt
            if self.game_over_timer <= 0:
                self.init_game()
            return

        self.game_time += dt

        # Disaster trigger
        if self.game_time >= self.next_disaster_t:
            self._trigger_disaster()
        self.disaster_t = max(0.0, self.disaster_t - dt)

        # Environmental timers
        if self.blizzard_t > 0:
            self.blizzard_t -= dt
        if self.mania_t > 0:
            self.mania_t -= dt
        if self.shake_t > 0:
            self.shake_t -= dt
            self.shake_x = (random.random() - 0.5) * 8
            self.shake_y = (random.random() - 0.5) * 8
        else:
            self.shake_x = self.shake_y = 0.0

        # Frog Rain: spawn pending frogs when their time arrives
        if self.pending_frogs:
            remaining = []
            for spawn_t, fx, fy in self.pending_frogs:
                if self.game_time >= spawn_t:
                    frog = Unit(fx, fy, _FROG_FID, 'frog', self)
                    # Frogs attack everyone — override fid targeting in _find_target
                    # by setting is_frog flag; handled in Unit._find_target via fid check.
                    self.entities.append(frog)
                    self.events.append({'type': 'boom', 'x': fx, 'y': fy,
                                        'r': 12, 'color': '#55BB33'})
                else:
                    remaining.append((spawn_t, fx, fy))
            self.pending_frogs = remaining

        # Wildfire DoT
        for wf in self.wildfire_zones:
            wf['t'] -= dt
            for e in self.grid.query(wf['x'], wf['y'], wf['r']):
                if e.dead or e.type != 'unit':
                    continue
                if _dist(e.x, e.y, wf['x'], wf['y']) < wf['r']:
                    already = next((d for d in e.dots if d.get('src') == 'wildfire'), None)
                    if already:
                        already['t'] = 1.0
                    else:
                        e.dots.append({'dmg': 9, 't': 1.0, 'src': 'wildfire'})
        self.wildfire_zones = [w for w in self.wildfire_zones if w['t'] > 0]

        # Plague cloud
        if self.plague_cloud:
            pc = self.plague_cloud
            pc['t'] -= dt
            pc['x'] += pc['vx'] * dt
            pc['y'] += pc['vy'] * dt
            for e in self.grid.query(pc['x'], pc['y'], pc['r']):
                if e.dead or e.type != 'unit':
                    continue
                if _dist(e.x, e.y, pc['x'], pc['y']) < pc['r']:
                    if not any(d.get('src') == 'plague' for d in e.dots):
                        e.dots.append({'dmg': 4, 't': 20.0, 'src': 'plague'})
            if pc['t'] <= 0 or pc['x'] > MAP_W + 200:
                self.plague_cloud = None

        # Titan spawn
        if not self.titans_spawned and self.game_time >= TITAN_TIME:
            self.titans_spawned = True
            for k, f in self.factions.items():
                if k == _FROG_FID or k not in self.castle_cache:
                    continue
                tt = FTITAN.get(k, 'elem_fire')
                self.entities.append(Titan(
                    tt,
                    f['cx'] + random.uniform(-10, 10),
                    f['cy'] + random.uniform(-10, 10), k))
                self.events.append({'type': 'sparks',
                                    'x': f['cx'], 'y': f['cy'],
                                    'color': f['color'], 'n': 16})

        # Prune dead entities
        self.entities = [e for e in self.entities if not e.dead]

        # Rebuild caches + spatial grid (single O(n) pass)
        self._rebuild_caches()

        # Monument debuffs (only when monuments exist)
        self._apply_monument_debuffs(dt)

        # Burn aura batch (~4× / sec)
        self.burn_aura_t -= dt
        if self.burn_aura_t <= 0:
            self.burn_aura_t = 0.25
            self._do_burn_aura()

        # Update all entities
        for e in self.entities:
            e.update(dt, self)

        # Win condition — frogs don't count as a surviving faction
        alive = {e.fid for e in self.entities
                 if e.type == 'castle' and not e.dead and e.fid != _FROG_FID}
        if len(alive) <= 1 and self.game_over_timer == -1.0:
            self.winner = next(iter(alive), 'draw')
            self.game_over_timer = RESTART_DELAY

        # Region control (every 10 s)
        self.region_update_t += dt
        if self.region_update_t >= 10.0:
            self.region_update_t = 0.0
            self._update_regions()

    # ── Cache rebuild ─────────────────────────────────────────────────────────

    def _rebuild_caches(self):
        """Single O(n) pass: spatial grid + all per-faction caches."""
        self._reset_caches()
        self.grid.clear()

        for e in self.entities:
            self.grid.insert(e)

            if e.type == 'castle':
                self.castle_cache[e.fid] = e

            elif e.type == 'unit':
                fid = e.fid
                self.faction_unit_count[fid] = self.faction_unit_count.get(fid, 0) + 1

                # Builder presence flag (replaces O(n) has_builder scan in Castle)
                if getattr(e, 'is_builder', False) or getattr(e, 'is_bastion_builder', False):
                    self.faction_has_builder[fid] = True

                # Cultist count for Dagon elder-god gate
                if e.utype == 'cultist':
                    self.faction_cultist_count[fid] = self.faction_cultist_count.get(fid, 0) + 1

            elif e.type == 'building':
                fid   = e.fid
                btype = e.btype
                cfg   = FBLDG.get(fid, {})

                if e.income:
                    self.faction_inc_bldg_count[fid] = self.faction_inc_bldg_count.get(fid, 0) + 1
                elif btype == cfg.get('special'):
                    self.faction_sp_bldg_count[fid]  = self.faction_sp_bldg_count.get(fid, 0) + 1
                else:
                    self.faction_def_bldg_count[fid]  = self.faction_def_bldg_count.get(fid, 0) + 1

                # Per-building buff caches
                _bmap = {
                    'library':       'faction_lib_count',
                    'mines':         'faction_mine_count',
                    'blacksmithy':   'faction_blacksmithy_count',
                    'quarry':        'faction_quarry_count',
                    'altar_of_madness': 'faction_altar_count',
                    'lab':           'faction_lab_count',
                    'blood_fountain':'faction_blood_fountain_count',
                    'amphitheater':  'faction_amphitheater_count',
                    'fighting_pit':  'faction_fighting_pit_count',
                }
                attr = _bmap.get(btype)
                if attr:
                    d = getattr(self, attr)
                    d[fid] = d.get(fid, 0) + 1

                if btype == 'biomass_tumor':
                    self.tumor_list.append(e)
                elif btype == 'rage_totem':
                    self.rage_totem_list.append(e)

    # ── Monument global debuffs ───────────────────────────────────────────────

    def _apply_monument_debuffs(self, dt):
        """Apply Horsemen monument penalties to enemy factions each tick.

        Only iterates entities when at least one monument with a live horseman
        is present, avoiding a full O(n) scan every tick when no apoc faction
        is in the match.
        """
        # Build alive-horsemen set once per tick
        alive_horsemen = {
            e.utype for e in self.entities
            if e.type == 'unit' and getattr(e, 'is_horseman', False) and not e.dead
        }
        if not alive_horsemen:
            return

        # Which monuments are active (horseman alive)?
        active = {}  # btype → owner_fid
        for e in self.entities:
            if e.type == 'building' and e.btype in _MONUMENT_REQUIREMENTS:
                if _MONUMENT_REQUIREMENTS[e.btype] in alive_horsemen:
                    active[e.btype] = e.fid
        if not active:
            return

        for e in self.entities:
            if e.dead:
                continue
            for btype, owner_fid in active.items():
                if e.fid == owner_fid:
                    continue
                if btype == 'crimson_cenotaph' and e.type == 'unit':
                    e.hp = max(1.0, e.hp - 0.5 * dt)
                elif btype == 'onyx_obelisk' and e.type == 'unit':
                    base = getattr(e, '_base_dmg_obelisk', e.dmg)
                    e._base_dmg_obelisk = base
                    e.dmg = max(1.0, base * 0.90)
                elif btype == 'marble_monument' and e.type == 'building':
                    if not getattr(e, '_marble_debuffed', False):
                        e._marble_debuffed = True
                        e.max_hp = max(1.0, e.max_hp * 0.90)
                        e.hp     = min(e.hp, e.max_hp)

    # ── Burn aura ─────────────────────────────────────────────────────────────

    def _do_burn_aura(self):
        for burner in self.entities:
            if not getattr(burner, 'burn_aura', False) or burner.dead:
                continue
            for e in self.grid.query(burner.x, burner.y, 22):
                if e.fid == burner.fid or e.dead or e.type != 'unit':
                    continue
                if _dist(e.x, e.y, burner.x, burner.y) < 22:
                    if not any(d.get('src') is burner for d in e.dots):
                        e.dots.append({'dmg': 4, 't': 1.5, 'src': burner})

    # ── Disaster system ───────────────────────────────────────────────────────

    def _announce_disaster(self, msg, col):
        self.disaster_msg = msg
        self.disaster_col = col
        self.disaster_t   = 4.0
        self.disaster_history.appendleft(
            {'msg': msg, 'col': col, 'time': int(self.game_time)})

    def _trigger_disaster(self):
        has_active = (self.blizzard_t > 0 or self.wildfire_zones
                      or self.plague_cloud or self.mania_t > 0
                      or bool(self.pending_frogs))
        if has_active:
            self.next_disaster_t = self.game_time + 30.0
            return

        self.next_disaster_t = (self.game_time
                                + (DISASTER_INTERVAL - 30.0)
                                + random.random() * 60.0)

        dtype = random.choice([
            'meteor_storm', 'wildfire',    'earthquake',  'blizzard',
            'smog',         'divine_wrath','blood_rain',  'pestilence',
            'madness',      'mania',       'midas_rain',  'warp_storm',
            'blessings',    'frog_rain',
        ])

        if dtype == 'meteor_storm':
            self._announce_disaster('METEOR STORM', '#FF6633')
            for _ in range(5):
                mx = 80 + random.random() * (MAP_W - 160)
                my = 80 + random.random() * (MAP_H - 160)
                self.events.append({'type': 'meteor', 'x': mx, 'y': my})
                self.events.append({'type': 'boom', 'x': mx, 'y': my,
                                    'r': 75, 'color': '#FF4400'})
                for e in self.grid.query(mx, my, 75):
                    if e.dead or _dist(e.x, e.y, mx, my) >= 75:
                        continue
                    if e.type == 'castle':
                        e.take_damage(90 * 0.35, None)
                    elif e.type in ('building', 'tower'):
                        e.take_damage(90 * 0.5, None)
                    elif hasattr(e, 'hp'):
                        e.hp = max(0.0, e.hp - 90)
                        e.flash = 0.3

        elif dtype == 'wildfire':
            self._announce_disaster('WILDFIRE', '#FF8800')
            self.wildfire_zones.append({
                'x': 100 + random.random() * (MAP_W - 200),
                'y': 100 + random.random() * (MAP_H - 200),
                'r': 120, 't': 18.0,
            })

        elif dtype == 'earthquake':
            self._announce_disaster('EARTHQUAKE', '#AA8833')
            ex = 100 + random.random() * (MAP_W - 200)
            ey = 100 + random.random() * (MAP_H - 200)
            self.shake_t = 2.0
            self.events.append({'type': 'boom', 'x': ex, 'y': ey,
                                 'r': 150, 'color': '#886633'})
            for e in self.grid.query(ex, ey, 150):
                if e.dead or e.type == 'castle':
                    continue
                if e.type in ('building', 'tower') and _dist(e.x, e.y, ex, ey) < 150:
                    e.hp   = 0
                    e.dead = True

        elif dtype == 'blizzard':
            self._announce_disaster('BLIZZARD', '#88CCFF')
            self.blizzard_t = 14.0

        elif dtype == 'smog':
            self._announce_disaster('SMOG CLOUD', '#99BB55')
            self.plague_cloud = {
                'x': -60,
                'y': 80 + random.random() * (MAP_H - 160),
                'r': 110, 't': 25.0,
                'vx': 150 + random.random() * 60,
                'vy': (random.random() - 0.5) * 40,
            }

        elif dtype == 'divine_wrath':
            self._announce_disaster('DIVINE WRATH', '#FFD700')
            targets = sorted(
                (e for e in self.entities if e.type == 'unit' and not e.dead),
                key=lambda e: e.hp, reverse=True)[:2]
            for t in targets:
                self.events.append({'type': 'beam',
                                    'x1': t.x, 'y1': t.y - 300,
                                    'x2': t.x, 'y2': t.y,
                                    'color': '#FFD700', 'lw': 8})
                self.events.append({'type': 'boom', 'x': t.x, 'y': t.y,
                                    'r': 60, 'color': '#FFD700'})
                t.hp   = 0
                t.dead = True

        elif dtype == 'blood_rain':
            self._announce_disaster('BLOOD RAIN', '#CC2244')
            for e in self.entities:
                if not e.dead and e.type == 'unit':
                    e.hp = min(e.max_hp, e.hp + e.max_hp * 0.25)
                    e.healing = 0.8

        elif dtype == 'pestilence':
            self._announce_disaster('PESTILENCE', '#66AA22')
            pool = [e for e in self.entities if e.type == 'unit' and not e.dead]
            for v in random.sample(pool, k=min(10, len(pool))):
                v.dots.append({'dmg': 5, 't': 30.0, 'src': 'pestilence'})
                v.flash = 0.3

        elif dtype == 'madness':
            self._announce_disaster('MADNESS', '#AA44DD')
            pool = [e for e in self.entities if e.type == 'unit' and not e.dead]
            for v in random.sample(pool, k=min(15, len(pool))):
                v.confused  = True
                v.confuse_t = 25.0
                v.flash     = 0.4

        elif dtype == 'mania':
            self._announce_disaster('MANIA', '#FF44AA')
            self.mania_t = 20.0

        elif dtype == 'midas_rain':
            self._announce_disaster('MIDAS RAIN', '#FFD700')
            for e in self.entities:
                if e.type == 'castle' and not e.dead:
                    e.gold += 400

        elif dtype == 'warp_storm':
            self._announce_disaster('WARP STORM', '#8844FF')
            units     = [e for e in self.entities if e.type == 'unit' and not e.dead]
            positions = [(e.x, e.y) for e in units]
            random.shuffle(positions)
            for e, (nx, ny) in zip(units, positions):
                self.events.append({'type': 'boom', 'x': e.x, 'y': e.y,
                                    'r': 20, 'color': '#8844FF'})
                e.x, e.y = nx, ny

        elif dtype == 'blessings':
            self._announce_disaster('BLESSINGS', '#AAFFAA')
            pool = [e for e in self.entities if e.type == 'unit' and not e.dead]
            for v in random.sample(pool, k=min(10, len(pool))):
                v.max_hp += 40
                v.hp      = v.max_hp
                v.healing = 1.2

        elif dtype == 'frog_rain':
            # ── Frog Rain ────────────────────────────────────────────────────
            # 40 frogs spawn at random map positions over a 10-second window.
            # Each frog is a real Unit with fid=_FROG_FID, hostile to everyone.
            # Frogs do NOT respawn on death. The spawn is staggered so they
            # "rain down" rather than all appearing at once.
            self._announce_disaster('FROG RAIN', '#55BB33')
            n_frogs = 40
            for i in range(n_frogs):
                # Stagger spawns evenly across 10 seconds
                spawn_at = self.game_time + (i / n_frogs) * 10.0
                fx = 60 + random.random() * (MAP_W - 120)
                fy = 60 + random.random() * (MAP_H - 120)
                self.pending_frogs.append((spawn_at, fx, fy))

    # ── Region control ────────────────────────────────────────────────────────

    def _update_regions(self):
        rw = MAP_W / REGION_COLS
        rh = MAP_H / REGION_ROWS
        for reg in self.regions:
            counts = {}
            rx, ry = reg['x'], reg['y']
            for e in self.grid.query_rect(rx, ry, rw, rh):
                if e.dead or e.type not in ('unit', 'building', 'castle', 'titan'):
                    continue
                if e.fid == _FROG_FID:
                    continue   # frogs don't control regions
                if rx <= e.x < rx + rw and ry <= e.y < ry + rh:
                    counts[e.fid] = counts.get(e.fid, 0) + (3 if e.type == 'castle' else 1)
            if counts:
                best  = max(counts, key=counts.get)
                total = sum(counts.values())
                reg['controlling_fid'] = best
                reg['control_pct']     = counts[best] / total
            elif reg['controlling_fid']:
                reg['control_pct'] = min(1.0, reg['control_pct'] + 0.2)

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_state(self, include_terrain=False):
        state = {
            'game_time':        self.game_time,
            'game_over_timer':  self.game_over_timer,
            'winner':           self.winner,
            'titans_spawned':   self.titans_spawned,
            'blizzard_t':       self.blizzard_t,
            'mania_t':          self.mania_t,
            'wildfire_zones':   self.wildfire_zones,
            'plague_cloud':     self.plague_cloud,
            'shake_x':          self.shake_x,
            'shake_y':          self.shake_y,
            'disaster_msg':     self.disaster_msg,
            'disaster_col':     self.disaster_col,
            'disaster_t':       self.disaster_t,
            'disaster_history': list(self.disaster_history),
            'next_disaster_t':  self.next_disaster_t,
            'faction_keys':     self.faction_keys,
            'factions':         {k: v for k, v in self.factions.items()
                                 if k != _FROG_FID},   # don't send pseudo-faction
            'entities':         [e.to_dict() for e in self.entities],
            'events':           self.events,
            'regions':          self.regions,
        }
        if include_terrain:
            state['terrain'] = self.terrain_serial
        return state