"""
Main simulation class. Owns all game state and advances it one dt step at a time.
The asyncio server calls tick() on a timer; between ticks the state is broadcast to clients.
"""
import math
import random
from .factions import (
    ALL_FACTIONS, STARTS, FTITAN, FBLDG,
    TITAN_TIME, RESTART_DELAY,
    REGION_NAMES, REGION_COLS, REGION_ROWS,
    MAP_W, MAP_H, pick_factions,
)
from .terrain import gen_terrain, terrain_to_serializable, in_river
from .entities import Castle, Unit, Building, ArrowTower, Titan, _dist


class Simulation:
    def __init__(self):
        self.game_time      = 0.0
        self.game_over_timer = -1.0
        self.winner         = None
        self.titans_spawned = False
        self.blizzard_t     = 0.0
        self.wildfire_zones = []
        self.plague_cloud   = None
        self.shake_x        = 0.0
        self.shake_y        = 0.0
        self.shake_t        = 0.0
        self.disaster_msg   = ''
        self.disaster_col   = '#FF8800'
        self.disaster_t     = 0.0
        self.disaster_history = []
        self.next_disaster_t  = 65.0 + random.random() * 50

        # Per-tick caches (rebuilt at start of tick)
        self.castle_cache      = {}
        self.faction_unit_count = {}
        self.tumor_list        = []
        self.rage_totem_list   = []
        self.burn_aura_t       = 0.0

        # Events emitted this tick — clients render particles for these
        self.events = []

        # Terrain and faction data
        self.faction_keys = []
        self.factions     = {}
        self.rivers       = []
        self.bridges      = []
        self.forests      = []
        self.terrain_serial = {}

        # Entity list
        self.entities = []

        # Region control — recomputed every ~10s
        self.regions = []
        self.region_update_t = 0.0

        self.init_game()

    # ── Init / reset ──────────────────────────────────────────────────────────

    def init_game(self):
        self.game_time       = 0.0
        self.game_over_timer = -1.0
        self.winner          = None
        self.titans_spawned  = False
        self.blizzard_t      = 0.0
        self.wildfire_zones  = []
        self.plague_cloud    = None
        self.shake_x = self.shake_y = self.shake_t = 0.0
        self.disaster_msg    = ''
        self.disaster_t      = 0.0
        self.disaster_history = []
        self.next_disaster_t = 65.0 + random.random() * 50
        self.castle_cache    = {}
        self.faction_unit_count = {}
        self.tumor_list      = []
        self.rage_totem_list = []
        self.burn_aura_t     = 0.0
        self.events          = []
        self.region_update_t = 0.0

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

        # Disasters
        if self.game_time >= self.next_disaster_t:
            self._trigger_disaster()
        self.disaster_t = max(0.0, self.disaster_t - dt)

        # Environmental effects
        if self.blizzard_t > 0:
            self.blizzard_t -= dt
        if self.shake_t > 0:
            self.shake_t -= dt
            self.shake_x = (random.random() - 0.5) * 8
            self.shake_y = (random.random() - 0.5) * 8
        else:
            self.shake_x = self.shake_y = 0.0

        # Wildfire
        for wf in self.wildfire_zones:
            wf['t'] -= dt
            for e in self.entities:
                if e.dead:
                    continue
                if e.type == 'unit' and _dist(e.x, e.y, wf['x'], wf['y']) < wf['r']:
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
            for e in self.entities:
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

        # Remove dead
        self.entities = [e for e in self.entities if not e.dead]

        # Rebuild caches
        self.castle_cache       = {}
        self.faction_unit_count = {}
        self.tumor_list         = []
        self.rage_totem_list    = []
        for e in self.entities:
            if e.type == 'castle':
                self.castle_cache[e.fid] = e
            elif e.type == 'unit':
                self.faction_unit_count[e.fid] = self.faction_unit_count.get(e.fid, 0) + 1
            elif e.type == 'building':
                if e.btype == 'tumor':
                    self.tumor_list.append(e)
                elif e.btype == 'rage_totem':
                    self.rage_totem_list.append(e)

        # Burn aura batch (~4× / sec)
        self.burn_aura_t -= dt
        if self.burn_aura_t <= 0:
            self.burn_aura_t = 0.25
            self._do_burn_aura()

        # Update entities
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

    # ── Burn aura ─────────────────────────────────────────────────────────────

    def _do_burn_aura(self):
        for burner in self.entities:
            if not getattr(burner, 'burn_aura', False) or burner.dead:
                continue
            for e in self.entities:
                if e.fid == burner.fid or e.dead:
                    continue
                if _dist(e.x, e.y, burner.x, burner.y) < 22:
                    if not any(d.get('src') is burner for d in e.dots):
                        e.dots.append({'dmg': 4, 't': 1.5, 'src': burner})

    # ── Disaster system ───────────────────────────────────────────────────────

    def _announce_disaster(self, msg, col):
        self.disaster_msg = msg
        self.disaster_col = col
        self.disaster_t   = 4.0
        entry = {'msg': msg, 'col': col, 'time': int(self.game_time)}
        self.disaster_history.insert(0, entry)
        if len(self.disaster_history) > 4:
            self.disaster_history.pop()

    def _trigger_disaster(self):
        self.next_disaster_t = self.game_time + 65.0 + random.random() * 50
        dtype = random.choice(['meteor', 'wildfire', 'earthquake', 'blizzard', 'plague', 'divine'])

        if dtype == 'meteor':
            self._announce_disaster('METEOR SHOWER', '#FF6633')
            for _ in range(4):
                mx = 80 + random.random() * (MAP_W - 160)
                my = 80 + random.random() * (MAP_H - 160)
                self.events.append({'type': 'meteor', 'x': mx, 'y': my})
                self.events.append({'type': 'boom', 'x': mx, 'y': my, 'r': 75, 'color': '#FF4400'})
                for e in self.entities:
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
            for e in self.entities:
                if e.dead or e.type == 'castle':
                    continue
                if e.type in ('building', 'tower') and _dist(e.x, e.y, ex, ey) < 150:
                    e.hp = 0
                    e.dead = True

        elif dtype == 'blizzard':
            self._announce_disaster('BLIZZARD', '#88CCFF')
            self.blizzard_t = 14.0

        elif dtype == 'plague':
            self._announce_disaster('PLAGUE CLOUD', '#44BB44')
            self.plague_cloud = {
                'x': -60, 'y': 80 + random.random() * (MAP_H - 160),
                'r': 90, 't': 20.0,
                'vx': 180 + random.random() * 60,
                'vy': (random.random() - 0.5) * 40,
            }

        elif dtype == 'divine':
            self._announce_disaster('DIVINE WRATH', '#FFD700')
            strongest = max(
                (e for e in self.entities if e.type == 'castle' and not e.dead),
                key=lambda e: e.hp + self.faction_unit_count.get(e.fid, 0) * 20,
                default=None)
            if strongest:
                self.events.append({'type': 'beam', 'x1': strongest.x, 'y1': strongest.y - 200,
                                    'x2': strongest.x, 'y2': strongest.y, 'color': '#FFD700', 'lw': 8})
                self.events.append({'type': 'boom', 'x': strongest.x, 'y': strongest.y, 'r': 100, 'color': '#FFD700'})
                strongest.take_damage(500, None)
                for e in self.entities:
                    if e.dead or e.type != 'unit':
                        continue
                    if _dist(e.x, e.y, strongest.x, strongest.y) < 100:
                        e.hp = max(0.0, e.hp - 80)
                        e.flash = 0.4

    # ── Region control ────────────────────────────────────────────────────────

    def _update_regions(self):
        rw = MAP_W / REGION_COLS
        rh = MAP_H / REGION_ROWS
        for reg in self.regions:
            counts = {}
            rx, ry = reg['x'], reg['y']
            for e in self.entities:
                if e.dead:
                    continue
                if e.type not in ('unit', 'building', 'castle', 'titan'):
                    continue
                if rx <= e.x < rx + rw and ry <= e.y < ry + rh:
                    counts[e.fid] = counts.get(e.fid, 0) + (3 if e.type == 'castle' else 1)
            if counts:
                best = max(counts, key=counts.get)
                total = sum(counts.values())
                reg['controlling_fid'] = best
                reg['control_pct'] = counts[best] / total
            else:
                reg['controlling_fid'] = None
                reg['control_pct'] = 0.0

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_state(self, include_terrain=False):
        state = {
            'game_time':       self.game_time,
            'game_over_timer': self.game_over_timer,
            'winner':          self.winner,
            'titans_spawned':  self.titans_spawned,
            'blizzard_t':      self.blizzard_t,
            'wildfire_zones':  self.wildfire_zones,
            'plague_cloud':    self.plague_cloud,
            'shake_x':         self.shake_x,
            'shake_y':         self.shake_y,
            'disaster_msg':    self.disaster_msg,
            'disaster_col':    self.disaster_col,
            'disaster_t':      self.disaster_t,
            'disaster_history': self.disaster_history,
            'next_disaster_t': self.next_disaster_t,
            'faction_keys':    self.faction_keys,
            'factions':        self.factions,
            'entities':        [e.to_dict() for e in self.entities],
            'events':          self.events,
            'regions':         self.regions,
        }
        if include_terrain:
            state['terrain'] = self.terrain_serial
        return state
