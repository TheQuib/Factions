"""
Main simulation class — updated for all new factions.
New per-tick caches added:
  faction_blood_fountain_count  — Sanguine Supplicants HP buff
  faction_amphitheater_count    — Celestial Choir stat buff
  faction_fighting_pit_count    — Goblin Gang dmg buff
  faction_quarry_count          — Bulwark Bastion structure HP buff
  faction_horseman_ever_bought  — Horsemen sequential purchase tracking
  apoc_monument_counts          — which Horseman monuments are active
Global debuff pass for Horsemen monuments applied each tick.
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

# Monument btype → required horseman utype
_MONUMENT_REQUIREMENTS = {
    'marble_monument':  'pestilence',
    'crimson_cenotaph': 'war_horseman',
    'onyx_obelisk':     'famine',
    'alabaster_angel':  'death_horseman',
}


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

        # Per-tick caches
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
        self.tumor_list                = []
        self.rage_totem_list           = []
        self.burn_aura_t               = 0.0

        # Horsemen tracking
        self.faction_horseman_ever_bought: dict[str, set] = {}

        self.grid = SpatialGrid(MAP_W, MAP_H)
        self.events = []

        self.faction_keys   = []
        self.factions       = {}
        self.rivers         = []
        self.bridges        = []
        self.forests        = []
        self.terrain_serial = {}

        self.entities = []

        self.regions         = []
        self.region_update_t = 0.0

        self.init_game()

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
        self.tumor_list       = []
        self.rage_totem_list  = []
        self.burn_aura_t      = 0.0

        self.faction_horseman_ever_bought = {}

        self.events           = []
        self.region_update_t  = 0.0

        self.faction_keys, self.factions = pick_factions()
        self.rivers, self.bridges, self.forests = gen_terrain()
        self.terrain_serial = terrain_to_serializable(self.rivers, self.bridges, self.forests)

        self.entities = []
        for k, f in self.factions.items():
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

        if self.game_time >= self.next_disaster_t:
            self._trigger_disaster()
        self.disaster_t = max(0.0, self.disaster_t - dt)

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

        # Wildfire
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
                if k not in self.castle_cache:
                    continue
                tt = FTITAN.get(k, 'elem_fire')
                self.entities.append(Titan(tt,
                    f['cx'] + random.uniform(-10, 10),
                    f['cy'] + random.uniform(-10, 10), k))
                self.events.append({'type': 'sparks', 'x': f['cx'], 'y': f['cy'],
                                    'color': f['color'], 'n': 16})

        # Prune dead
        self.entities = [e for e in self.entities if not e.dead]

        # Rebuild caches + spatial grid
        self._rebuild_caches()

        # ── Global Horsemen monument debuffs ──────────────────────────────────
        self._apply_monument_debuffs(dt)

        # Burn aura
        self.burn_aura_t -= dt
        if self.burn_aura_t <= 0:
            self.burn_aura_t = 0.25
            self._do_burn_aura()

        # Update all entities
        for e in self.entities:
            e.update(dt, self)

        # Win condition
        alive = {e.fid for e in self.entities if e.type == 'castle' and not e.dead}
        if len(alive) <= 1 and self.game_over_timer == -1.0:
            self.winner = next(iter(alive), 'draw')
            self.game_over_timer = RESTART_DELAY

        # Regions
        self.region_update_t += dt
        if self.region_update_t >= 10.0:
            self.region_update_t = 0.0
            self._update_regions()

    # ── Cache rebuild ─────────────────────────────────────────────────────────

    def _rebuild_caches(self):
        """Single O(n) pass: spatial grid + all faction caches."""
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
        self.tumor_list                = []
        self.rage_totem_list           = []

        self.grid.clear()

        for e in self.entities:
            self.grid.insert(e)

            if e.type == 'castle':
                self.castle_cache[e.fid] = e

            elif e.type == 'unit':
                self.faction_unit_count[e.fid] = self.faction_unit_count.get(e.fid, 0) + 1

            elif e.type == 'building':
                fid   = e.fid
                btype = e.btype
                cfg   = FBLDG.get(fid, {})

                if e.income:
                    self.faction_inc_bldg_count[fid] = self.faction_inc_bldg_count.get(fid, 0) + 1
                elif btype == cfg.get('special'):
                    self.faction_sp_bldg_count[fid] = self.faction_sp_bldg_count.get(fid, 0) + 1
                else:
                    self.faction_def_bldg_count[fid] = self.faction_def_bldg_count.get(fid, 0) + 1

                # Per-building buff caches
                if btype == 'library':
                    self.faction_lib_count[fid] = self.faction_lib_count.get(fid, 0) + 1
                elif btype == 'mines':
                    self.faction_mine_count[fid] = self.faction_mine_count.get(fid, 0) + 1
                elif btype == 'blacksmithy':
                    self.faction_blacksmithy_count[fid] = self.faction_blacksmithy_count.get(fid, 0) + 1
                elif btype == 'quarry':
                    self.faction_quarry_count[fid] = self.faction_quarry_count.get(fid, 0) + 1
                elif btype == 'altar_of_madness':
                    self.faction_altar_count[fid] = self.faction_altar_count.get(fid, 0) + 1
                elif btype == 'lab':
                    self.faction_lab_count[fid] = self.faction_lab_count.get(fid, 0) + 1
                elif btype == 'blood_fountain':
                    self.faction_blood_fountain_count[fid] = self.faction_blood_fountain_count.get(fid, 0) + 1
                elif btype == 'amphitheater':
                    self.faction_amphitheater_count[fid] = self.faction_amphitheater_count.get(fid, 0) + 1
                elif btype == 'fighting_pit':
                    self.faction_fighting_pit_count[fid] = self.faction_fighting_pit_count.get(fid, 0) + 1

                if btype == 'biomass_tumor':
                    self.tumor_list.append(e)
                elif btype == 'rage_totem':
                    self.rage_totem_list.append(e)

    # ── Horsemen monument global debuffs ──────────────────────────────────────

    def _apply_monument_debuffs(self, dt):
        """
        For each Horseman monument that exists AND whose Horseman is alive,
        apply the corresponding global penalty to all enemy entities each tick.

        marble_monument   → enemy buildings lose 10% max HP (applied once on discovery)
        crimson_cenotaph  → enemy units lose 0.5 HP/s (as a DoT)
        onyx_obelisk      → enemy units have dmg reduced by 10% (clamped, applied per tick)
        alabaster_angel   → handled in Building.update (kills 1 unit/5s)
        """
        # Collect which monuments exist per apoc faction and which horsemen are alive
        monuments = {}   # btype → fid
        alive_horsemen = {
            e.utype for e in self.entities
            if e.type == 'unit' and getattr(e, 'is_horseman', False) and not e.dead
        }

        for e in self.entities:
            if e.type == 'building' and e.btype in _MONUMENT_REQUIREMENTS:
                required = _MONUMENT_REQUIREMENTS[e.btype]
                if required in alive_horsemen:
                    monuments[e.btype] = e.fid

        if not monuments:
            return

        for e in self.entities:
            if e.dead:
                continue
            fid = e.fid
            # Check if this entity belongs to an enemy of any apoc monument owner
            for btype, owner_fid in monuments.items():
                if fid == owner_fid:
                    continue   # don't debuff own faction

                if btype == 'crimson_cenotaph' and e.type == 'unit':
                    # -0.5 HP/s continuous drain
                    e.hp = max(1.0, e.hp - 0.5 * dt)

                elif btype == 'onyx_obelisk' and e.type == 'unit':
                    # -10% dmg per tick (floor at 1)
                    base_dmg = getattr(e, '_base_dmg_before_obelisk', e.dmg)
                    e._base_dmg_before_obelisk = base_dmg
                    e.dmg = max(1.0, base_dmg * 0.90)

                elif btype == 'marble_monument' and e.type == 'building':
                    # Apply once: reduce max HP by 10%
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
        self.disaster_history.appendleft({'msg': msg, 'col': col, 'time': int(self.game_time)})

    def _trigger_disaster(self):
        has_active = (self.blizzard_t > 0 or self.wildfire_zones or
                      self.plague_cloud or self.mania_t > 0)
        if has_active:
            self.next_disaster_t = self.game_time + 30.0
            return

        self.next_disaster_t = self.game_time + (DISASTER_INTERVAL - 30.0) + random.random() * 60.0

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
                self.events.append({'type': 'boom', 'x': mx, 'y': my, 'r': 75, 'color': '#FF4400'})
                for e in self.grid.query(mx, my, 75):
                    if e.dead:
                        continue
                    if _dist(e.x, e.y, mx, my) < 75:
                        if e.type == 'castle':
                            e.take_damage(90 * 0.35, None)
                        elif e.type in ('building', 'tower'):
                            e.take_damage(90 * 0.5, None)
                        elif hasattr(e, 'hp'):
                            e.hp = max(0.0, e.hp - 90)
                            e.flash = 0.3

        elif dtype == 'wildfire':
            self._announce_disaster('WILDFIRE', '#FF8800')
            wx = 100 + random.random() * (MAP_W - 200)
            wy = 100 + random.random() * (MAP_H - 200)
            self.wildfire_zones.append({'x': wx, 'y': wy, 'r': 120, 't': 18.0})

        elif dtype == 'earthquake':
            self._announce_disaster('EARTHQUAKE', '#AA8833')
            ex = 100 + random.random() * (MAP_W - 200)
            ey = 100 + random.random() * (MAP_H - 200)
            self.shake_t = 2.0
            self.events.append({'type': 'boom', 'x': ex, 'y': ey, 'r': 150, 'color': '#886633'})
            for e in self.grid.query(ex, ey, 150):
                if e.dead or e.type == 'castle':
                    continue
                if e.type in ('building', 'tower') and _dist(e.x, e.y, ex, ey) < 150:
                    e.hp = 0
                    e.dead = True

        elif dtype == 'blizzard':
            self._announce_disaster('BLIZZARD', '#88CCFF')
            self.blizzard_t = 14.0

        elif dtype == 'smog':
            self._announce_disaster('SMOG CLOUD', '#99BB55')
            self.plague_cloud = {
                'x': -60, 'y': 80 + random.random() * (MAP_H - 160),
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
                self.events.append({'type': 'beam', 'x1': t.x, 'y1': t.y - 300,
                                    'x2': t.x, 'y2': t.y, 'color': '#FFD700', 'lw': 8})
                self.events.append({'type': 'boom', 'x': t.x, 'y': t.y, 'r': 60, 'color': '#FFD700'})
                t.hp = 0
                t.dead = True

        elif dtype == 'blood_rain':
            self._announce_disaster('BLOOD RAIN', '#CC2244')
            for e in self.entities:
                if e.dead or e.type != 'unit':
                    continue
                e.hp = min(e.max_hp, e.hp + e.max_hp * 0.25)
                e.healing = 0.8

        elif dtype == 'pestilence':
            self._announce_disaster('PESTILENCE', '#66AA22')
            candidates = [e for e in self.entities if e.type == 'unit' and not e.dead]
            victims = random.sample(candidates, k=min(10, len(candidates)))
            for v in victims:
                v.dots.append({'dmg': 5, 't': 30.0, 'src': 'pestilence'})
                v.flash = 0.3

        elif dtype == 'madness':
            self._announce_disaster('MADNESS', '#AA44DD')
            candidates = [e for e in self.entities if e.type == 'unit' and not e.dead]
            for v in random.sample(candidates, k=min(15, len(candidates))):
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
                self.events.append({'type': 'boom', 'x': e.x, 'y': e.y, 'r': 20, 'color': '#8844FF'})
                e.x, e.y = nx, ny

        elif dtype == 'blessings':
            self._announce_disaster('BLESSINGS', '#AAFFAA')
            candidates = [e for e in self.entities if e.type == 'unit' and not e.dead]
            for v in random.sample(candidates, k=min(10, len(candidates))):
                v.max_hp += 40
                v.hp      = v.max_hp
                v.healing = 1.2

        elif dtype == 'frog_rain':
            self._announce_disaster('FROG RAIN', '#55BB33')
            for _ in range(10):
                fx = 60 + random.random() * (MAP_W - 120)
                fy = 60 + random.random() * (MAP_H - 120)
                self.events.append({'type': 'boom', 'x': fx, 'y': fy, 'r': 40, 'color': '#55BB33'})
                for e in self.grid.query(fx, fy, 40):
                    if e.dead or e.type != 'unit':
                        continue
                    if _dist(e.x, e.y, fx, fy) < 40:
                        e.hp = max(0.0, e.hp - 20)
                        e.flash = 0.2

    # ── Region control ────────────────────────────────────────────────────────

    def _update_regions(self):
        rw = MAP_W / REGION_COLS
        rh = MAP_H / REGION_ROWS
        for reg in self.regions:
            counts = {}
            rx, ry = reg['x'], reg['y']
            for e in self.grid.query_rect(rx, ry, rw, rh):
                if e.dead:
                    continue
                if e.type not in ('unit', 'building', 'castle', 'titan'):
                    continue
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
            'factions':         self.factions,
            'entities':         [e.to_dict() for e in self.entities],
            'events':           self.events,
            'regions':          self.regions,
        }
        if include_terrain:
            state['terrain'] = self.terrain_serial
        return state