import math
import random
from .factions import (
    MAP_W, MAP_H, UTYPES, SPAWN_POOLS, FBLDG, FTITAN,
    PASSIVE_GOLD, BUILD_GOLD, SWARM_THRESHOLD,
    MAX_INC_BLDG, MAX_DEF_BLDG, MAX_SPECIAL, MAX_UNITS_PER_FACTION,
    FACTION_UNIT_CAPS, FACTION_SPAWN_INTERVAL,
    TOWER_EXPIRE, TITAN_TIME,
)
from .terrain import terrain_speed, get_waypoint, in_river

_next_id = 0


def _new_id():
    global _next_id
    _next_id += 1
    return _next_id


def _dist(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


# ─── Shared helpers ───────────────────────────────────────────────────────────

def _apply_dot(e, dmg, duration, src):
    """Append or refresh a named DoT on entity e.
    Safe to call on any entity type — silently skips Buildings, Castles,
    and Titans which have no .dots attribute.
    """
    dots = getattr(e, 'dots', None)
    if dots is None:
        return
    existing = next((d for d in dots if d.get('src') == src), None)
    if existing:
        existing['t'] = max(existing['t'], duration)
    else:
        dots.append({'dmg': dmg, 't': duration, 'src': src})


def _chain_hit(sim, hits, prev, dmg, fid, chain_r=120, dmg_mult=0.55):
    """Walk one chain-lightning bounce; appends beam event. Returns next target or None."""
    nxt, nd = None, float(chain_r)
    for e in sim.grid.query(prev.x, prev.y, chain_r):
        if e.fid == fid or e.dead or e in hits:
            continue
        d = _dist(e.x, e.y, prev.x, prev.y)
        if d < nd:
            nd, nxt = d, e
    if nxt:
        nxt.hp = max(0.0, nxt.hp - dmg * dmg_mult)
        nxt.flash = 0.12
        sim.events.append({'type': 'beam',
                           'x1': prev.x, 'y1': prev.y,
                           'x2': nxt.x,  'y2': nxt.y,
                           'color': '#AADDFF', 'lw': 2})
        hits.append(nxt)
    return nxt


def _aoe_hit(sim, cx, cy, radius, dmg, owner_fid, color, exclude=None):
    """Deal dmg to all enemies within radius; emit boom event."""
    sim.events.append({'type': 'boom', 'x': cx, 'y': cy, 'r': radius, 'color': color})
    for e in sim.grid.query(cx, cy, radius):
        if e.fid == owner_fid or e.dead or e is exclude:
            continue
        if _dist(e.x, e.y, cx, cy) < radius:
            if e.type == 'unit':
                e.hp = max(0.0, e.hp - dmg)
                e.flash = 0.12
            elif e.type == 'building':
                e.take_damage(dmg * 0.5, owner_fid)
            elif e.type == 'castle':
                e.take_damage(dmg * 0.2, owner_fid)


# ─── Arrow Tower ──────────────────────────────────────────────────────────────

class ArrowTower:
    def __init__(self, x, y):
        self.id       = _new_id()
        self.x, self.y = x, y
        self.type     = 'tower'
        self.fid      = 'neutral'
        self.hp       = self.max_hp = 200
        self.dead     = False
        self.flash    = 0.0
        self.cd       = 1.0 + random.random()
        self.rng      = 140
        self.dmg      = 14
        self.atk_spd  = 2.0
        self.last_hit_by = None
        self.inc_t    = 0.0

    def update(self, dt, sim):
        if sim.game_time >= TOWER_EXPIRE:
            self.dead = True
            sim.events.append({'type': 'death', 'x': self.x, 'y': self.y, 'color': '#888888'})
            return
        self.flash = max(0.0, self.flash - dt)
        self.cd   -= dt
        if self.fid != 'neutral':
            self.inc_t += dt
            if self.inc_t >= 1.0:
                self.inc_t = 0.0
                c = sim.castle_cache.get(self.fid)
                if c:
                    c.gold += 0.3
        if self.cd > 0:
            return
        tgt, bd = None, self.rng
        for e in sim.grid.query(self.x, self.y, self.rng):
            if e.dead:
                continue
            if self.fid != 'neutral' and e.fid == self.fid:
                continue
            if self.fid == 'neutral' and e.type == 'castle':
                continue
            d = _dist(e.x, e.y, self.x, self.y)
            if d < bd:
                bd, tgt = d, e
        if not tgt:
            self.cd = 0.6
            return
        dmg = self.dmg + (random.random() - 0.5) * 5
        if tgt.type == 'castle':
            tgt.take_damage(dmg * 0.25, self.fid)
        elif tgt.type in ('building', 'tower'):
            tgt.take_damage(dmg * 0.6, self.fid)
        else:
            tgt.hp = max(0.0, tgt.hp - dmg)
            tgt.flash = 0.15
            if hasattr(tgt, 'combat_t'):
                tgt.combat_t = 0.0
        sim.events.append({'type': 'beam', 'x1': self.x, 'y1': self.y,
                           'x2': tgt.x, 'y2': tgt.y, 'color': '#AAAA44', 'lw': 1.5})
        self.cd = self.atk_spd

    def take_damage(self, d, attacker_fid):
        self.hp = max(0.0, self.hp - d)
        self.flash = 0.2
        if attacker_fid and attacker_fid != 'neutral':
            self.last_hit_by = attacker_fid
        if self.hp <= 0:
            if self.last_hit_by:
                self.fid = self.last_hit_by
                self.hp  = self.max_hp * 0.5
            else:
                self.dead = True

    def to_dict(self):
        return {'id': self.id, 'type': 'tower', 'fid': self.fid,
                'x': self.x, 'y': self.y, 'hp': self.hp, 'max_hp': self.max_hp,
                'flash': self.flash}


# ─── Building ─────────────────────────────────────────────────────────────────

_INCOME_BTYPES = frozenset({
    'granary', 'shrine', 'mycelium', 'ossuary', 'forge', 'blood_altar',
    'foundry', 'dream_spire', 'farm', 'library', 'stonecircle',
    'biomass_tumor', 'forest', 'blacksmithy', 'graveyard', 'fungal_patch',
    'quarry', 'altar_of_madness', 'lab', 'mines', 'amphitheater',
    'blood_fountain', 'gnomish_workshop', 'mann_farm', 'fighting_pit', 'cairn',
})

# Buildings that spawn units on a timer — (spawn_cd, max_minions, utype_or_list)
# Using a flat lookup avoids repeated btype string comparisons in update().
_SPAWNER_BTYPES = {
    'def_hive':        (8,  6,  'hive_swarm'),
    'crypt':           (12, 10, 'crypt_archer'),
    'community_center':(20, None, ['choir_fan'] * 8),   # spawns a wave, no cap
}

_BLDG_STATS = {
    # ── Generic / legacy ───────────────────────────────────────────────────────
    'farm':             {'hp': 250},
    'library':          {'hp': 200},
    'stonecircle':      {'hp': 200},
    'granary':          {'hp': 220},
    'ossuary':          {'hp': 200},
    'rampart':          {'hp': 450},
    'shadow_trap':      {'hp': 180, 'rng': 100, 'dmg': 22, 'atk_spd': 2.5, 'cd': 1.0},
    'storm_totem':      {'hp': 200, 'rng': 140, 'dmg': 14, 'atk_spd': 1.6, 'cd': 1.0, 'chains': 2},
    'frost_shrine':     {'hp': 220},
    'ice_wall':         {'hp': 380, 'rng': 120, 'dmg': 10, 'atk_spd': 2.0, 'cd': 1.0, 'frost_slow': True},
    'forge':            {'hp': 200},
    'fire_pit':         {'hp': 220, 'rng': 90,  'dmg': 15, 'atk_spd': 1.5, 'cd': 1.0, 'burn_aura': True},
    'shrine':           {'hp': 200},
    'beacon':           {'hp': 200, 'heal_r': 90,  'heal_rate': 5,  'heal_cd': 0.4},
    'harbor':           {'hp': 200},
    'tide_shrine':      {'hp': 200, 'rng': 130, 'dmg': 14, 'atk_spd': 1.8, 'cd': 1.0, 'aoe': 45},
    'blood_altar':      {'hp': 200},
    'rage_totem':       {'hp': 180},
    'death_shrine':     {'hp': 200, 'rng': 120, 'dmg': 16, 'atk_spd': 2.0, 'cd': 1.0, 'raise_dead': True},
    'spore_tower':      {'hp': 200, 'rng': 120, 'dmg': 8,  'atk_spd': 1.5, 'cd': 1.0, 'aoe': 40},
    'dream_spire':      {'hp': 200},
    'veil_shrine':      {'hp': 180, 'rng': 130, 'dmg': 10, 'atk_spd': 2.0, 'cd': 1.0, 'confuses': True},
    'stable':           {'hp': 200},
    'thieves_den':      {'hp': 200},
    # ── Hemophage Hive ─────────────────────────────────────────────────────────
    'biomass_tumor':    {'hp': 120, 'aoe_spd_r': 60.0, 'aoe_spd_max': 180.0, 'aoe_grow_rate': 0.4},
    'def_hive':         {'hp': 280, 'spawn_cd': 8,  'spawn_t': 4},
    # ── Arcane Academy ─────────────────────────────────────────────────────────
    'arcane_turret':    {'hp': 220, 'rng': 160, 'dmg': 20, 'atk_spd': 1.8, 'cd': 2.0, 'arcane_turret': True},
    # ── Sylvan Stewards ────────────────────────────────────────────────────────
    'forest':           {'hp': 320, 'zone_r': 75},
    'bramble_patch':    {'hp': 200, 'bramble': True},
    # ── Lux Legionis ───────────────────────────────────────────────────────────
    'blacksmithy':      {'hp': 240},
    'church':           {'hp': 300, 'heal_r': 90,  'heal_rate': 5,  'heal_cd': 0.4},
    # ── Gnomish Gearsmiths ─────────────────────────────────────────────────────
    'gnomish_workshop': {'hp': 300, 'workshop_explode': True},
    'minefield':        {'hp': 180, 'minefield': True, 'mine_cd': 12.0},
    # ── Cryptlord Cabal ────────────────────────────────────────────────────────
    'graveyard':        {'hp': 280, 'spawn_cd': 18, 'spawn_t': 18},
    'crypt':            {'hp': 320, 'spawn_cd': 12, 'spawn_t': 10},
    # ── Mycelium Multitude ─────────────────────────────────────────────────────
    'fungal_patch':     {'hp': 180, 'fungal_patch': True},
    'sporolith':        {'hp': 160, 'rng': 50.0,  'dmg': 5,  'atk_spd': 1.2, 'cd': 1.2,
                         'aoe': 50.0, 'grow_aoe': True, 'aoe_max': 160.0, 'aoe_grow_rate': 0.15},
    # ── Celestial Choir ────────────────────────────────────────────────────────
    'amphitheater':     {'hp': 220},
    'community_center': {'hp': 280, 'spawn_cd': 20, 'spawn_t': 20},
    # ── Sanguine Supplicants ───────────────────────────────────────────────────
    'blood_fountain':   {'hp': 200},
    'bloodstone':       {'hp': 180, 'rng': 100, 'dmg': 6,  'atk_spd': 1.0, 'cd': 1.0, 'bloodstone': True},
    # ── Fabricator Forges ──────────────────────────────────────────────────────
    'mines':            {'hp': 220},
    'flamethrower':     {'hp': 200, 'rng': 100, 'dmg': 18, 'atk_spd': 1.2, 'cd': 1.2, 'cone_aoe': True},
    # ── Bulwark Bastion ────────────────────────────────────────────────────────
    'quarry':           {'hp': 220},
    'bastila':          {'hp': 250, 'rng': 180, 'dmg': 35, 'atk_spd': 2.5, 'cd': 2.5},
    'bwall':            {'hp': 500, 'is_wall': True},
    'bgate':            {'hp': 350, 'is_gate': True},
    'btower':           {'hp': 300, 'rng': 150, 'dmg': 20, 'atk_spd': 2.0, 'cd': 2.0},
    # ── Dreamers of Dagon ──────────────────────────────────────────────────────
    'altar_of_madness': {'hp': 200},
    'void_rift':        {'hp': 220, 'rng': 55,  'dmg': 20, 'atk_spd': 1.0, 'cd': 1.0, 'aoe': 55},
    # ── Hostile Hospice ────────────────────────────────────────────────────────
    'lab':              {'hp': 200},
    'toxic_smokestack': {'hp': 180, 'rng': 60.0, 'dmg': 4,  'atk_spd': 1.5, 'cd': 1.5,
                         'aoe': 60.0, 'grow_aoe': True, 'aoe_max': 200.0, 'aoe_grow_rate': 0.08},
    # ── Empire of Man ──────────────────────────────────────────────────────────
    'mann_farm':        {'hp': 240, 'mann_farm': True},
    'archer_tower':     {'hp': 260, 'rng': 160, 'dmg': 18, 'atk_spd': 2.0, 'cd': 2.0},
    # ── Goblin Gang ────────────────────────────────────────────────────────────
    'fighting_pit':     {'hp': 180},
    'pitfall_trap':     {'hp': 150, 'pitfall': True, 'pitfall_r': 55, 'pitfall_dmg': 40, 'pitfall_cd': 8.0},
    # ── Horsemen of the Apocalypse ─────────────────────────────────────────────
    'cairn':            {'hp': 180},
    'marble_monument':  {'hp': 300},
    'crimson_cenotaph': {'hp': 300},
    'onyx_obelisk':     {'hp': 300},
    'alabaster_angel':  {'hp': 300, 'angel_cd': 5.0},
}


class Building:
    def __init__(self, x, y, fid, btype):
        self.id      = _new_id()
        self.x, self.y = x, y
        self.fid     = fid
        self.btype   = btype
        self.type    = 'building'
        self.dead    = False
        self.flash   = 0.0
        stats        = _BLDG_STATS.get(btype, {'hp': 200})

        self.hp = self.max_hp = float(stats.get('hp', 200))
        self.income    = btype in _INCOME_BTYPES
        self.inc_t     = 0.0
        self.heal_t    = 0.0
        self.zone_t    = 0.0
        self.rng       = float(stats.get('rng', 0))
        self.dmg       = float(stats.get('dmg', 0))
        self.atk_spd   = float(stats.get('atk_spd', 0))
        self.cd        = float(stats.get('cd', 0.0))
        self.chains    = stats.get('chains', 0)
        self.aoe       = float(stats.get('aoe', 0))
        self.frost_slow    = stats.get('frost_slow', False)
        self.raise_dead    = stats.get('raise_dead', False)
        self.confuses      = stats.get('confuses', False)
        self.burn_aura     = stats.get('burn_aura', False)
        self.arcane_turret = stats.get('arcane_turret', False)
        self.cone_aoe      = stats.get('cone_aoe', False)
        self.bramble       = stats.get('bramble', False)
        self.bramble_cd    = 0.0
        self.is_wall       = stats.get('is_wall', False)
        self.is_gate       = stats.get('is_gate', False)
        self.fungal_patch  = stats.get('fungal_patch', False)
        self.grow_aoe      = stats.get('grow_aoe', False)
        self.aoe_max       = float(stats.get('aoe_max', self.aoe))
        self.aoe_grow_rate = float(stats.get('aoe_grow_rate', 0.0))
        self.heal_r        = float(stats.get('heal_r', 0))
        self.heal_rate     = float(stats.get('heal_rate', 0))
        self.heal_cd       = float(stats.get('heal_cd', 0))
        self.zone_r        = float(stats.get('zone_r', 0))
        self.spawn_cd      = float(stats.get('spawn_cd', 0))
        self.spawn_t       = float(stats.get('spawn_t', 0))
        self.minions       = []
        self.aoe_spd_r     = float(stats.get('aoe_spd_r', 0))
        self.aoe_spd_max   = float(stats.get('aoe_spd_max', 0))
        self.expiry_t      = stats.get('expiry_t', None)
        # Bloodstone state
        self.bloodstone    = stats.get('bloodstone', False)
        self.bs_target     = None
        # Pitfall state
        self.pitfall       = stats.get('pitfall', False)
        self.pitfall_r     = float(stats.get('pitfall_r', 55))
        self.pitfall_dmg   = float(stats.get('pitfall_dmg', 40))
        self.pitfall_cd    = float(stats.get('pitfall_cd', 8.0))
        self.pitfall_t     = 0.0
        # Workshop state
        self.workshop_explode = stats.get('workshop_explode', False)
        self.workshop_t    = random.uniform(60, 180)
        # Minefield state
        self.minefield     = stats.get('minefield', False)
        self.mine_cd       = float(stats.get('mine_cd', 12.0))
        self.mine_t        = self.mine_cd
        # Mann Farm growth
        self.mann_farm     = stats.get('mann_farm', False)
        self.farm_rate     = BUILD_GOLD
        self.farm_upgrade_t = 0.0
        # Alabaster Angel
        self.angel_cd      = float(stats.get('angel_cd', 0.0))
        self.angel_t       = self.angel_cd
        # Back-reference set by placing code so bramble/bastion can reach the sim
        self._sim_ref      = None

    # ── Income ────────────────────────────────────────────────────────────────

    def _tick_income(self, dt, sim):
        self.inc_t += dt
        if self.inc_t < 1.0:
            return
        self.inc_t = 0.0
        c = sim.castle_cache.get(self.fid)
        if c:
            rate = self.farm_rate if self.mann_farm else BUILD_GOLD
            c.gold += rate

    # ── Spawner buildings (def_hive, crypt, graveyard, community_center) ──────

    def _tick_spawner(self, dt, sim):
        """Single unified spawner path for all timed-spawn buildings."""
        self.spawn_t -= dt
        if self.spawn_t > 0:
            return
        self.spawn_t = self.spawn_cd

        if self.btype == 'graveyard':
            for utype in ('zombie', 'crypt_skeleton'):
                u = Unit(self.x + random.uniform(-20, 20),
                         self.y + random.uniform(-20, 20),
                         self.fid, utype, sim)
                sim.entities.append(u)
            return

        if self.btype == 'community_center':
            for _ in range(8):
                ang = random.random() * math.pi * 2
                u = Unit(self.x + math.cos(ang) * 20, self.y + math.sin(ang) * 20,
                         self.fid, 'choir_fan', sim)
                sim.entities.append(u)
            sim.events.append({'type': 'boom', 'x': self.x, 'y': self.y,
                               'r': 40, 'color': '#FFD700'})
            return

        # def_hive → hive_swarm (cap 6), crypt → crypt_archer (cap 10)
        cfg = _SPAWNER_BTYPES.get(self.btype)
        if cfg:
            _, cap, utype = cfg
            self.minions = [m for m in self.minions if not m.dead and m.hp > 0]
            if cap is None or len(self.minions) < cap:
                ang = random.random() * math.pi * 2
                u = Unit(self.x + math.cos(ang) * 20, self.y + math.sin(ang) * 20,
                         self.fid, utype, sim)
                u.home_building = self
                sim.entities.append(u)
                self.minions.append(u)

    # ── Main update ───────────────────────────────────────────────────────────

    def update(self, dt, sim):
        self.flash = max(0.0, self.flash - dt)

        # Temporary structure expiry (engineer turrets, deployed mines)
        if self.expiry_t is not None:
            self.expiry_t -= dt
            if self.expiry_t <= 0:
                self.dead = True
                sim.events.append({'type': 'death', 'x': self.x, 'y': self.y,
                                   'color': '#888888'})
                return

        if self.income:
            self._tick_income(dt, sim)

        # Mann Farm income growth: +0.05 gold/s per 30s survived, capped at 3× base
        if self.mann_farm:
            self.farm_upgrade_t += dt
            if self.farm_upgrade_t >= 30.0:
                self.farm_upgrade_t = 0.0
                self.farm_rate = min(BUILD_GOLD * 3.0, self.farm_rate + 0.05)

        # Growing AoE (sporolith, toxic_smokestack)
        if self.grow_aoe and self.aoe < self.aoe_max:
            self.aoe = min(self.aoe_max, self.aoe + self.aoe_grow_rate * dt)
            self.rng = self.aoe

        # Biomass tumor: grow speed-buff radius
        if self.btype == 'biomass_tumor' and self.aoe_spd_r < self.aoe_spd_max:
            self.aoe_spd_r = min(self.aoe_spd_max,
                                 self.aoe_spd_r + _BLDG_STATS['biomass_tumor']['aoe_grow_rate'] * dt)

        # Spawner buildings (unified path)
        if self.btype in ('def_hive', 'graveyard', 'crypt', 'community_center'):
            self._tick_spawner(dt, sim)

        # Gnomish Workshop random explosion
        if self.workshop_explode:
            self.workshop_t -= dt
            if self.workshop_t <= 0:
                self.workshop_t = random.uniform(60, 240)
                if random.random() < 0.30:
                    _aoe_hit(sim, self.x, self.y, 80, 60, self.fid, '#FFAA22')
                    self.hp = max(0.0, self.hp - 150)
                    if self.hp <= 0:
                        self.dead = True
                        return

        # Minefield: periodically place a mine (pitfall_trap) nearby
        if self.minefield:
            self.mine_t -= dt
            if self.mine_t <= 0:
                self.mine_t = self.mine_cd
                ang  = random.random() * math.pi * 2
                r    = random.uniform(20, 90)
                mine = Building(self.x + math.cos(ang) * r,
                                self.y + math.sin(ang) * r,
                                self.fid, 'pitfall_trap')
                mine.expiry_t  = 45.0
                mine._sim_ref  = sim
                sim.entities.append(mine)

        # Pitfall trap: trigger on any enemy unit entering radius
        if self.pitfall:
            self.pitfall_t = max(0.0, self.pitfall_t - dt)
            if self.pitfall_t <= 0:
                triggered = any(
                    e.fid != self.fid and not e.dead and e.type == 'unit'
                    and _dist(e.x, e.y, self.x, self.y) < self.pitfall_r
                    for e in sim.grid.query(self.x, self.y, self.pitfall_r)
                )
                if triggered:
                    _aoe_hit(sim, self.x, self.y, self.pitfall_r,
                             self.pitfall_dmg, self.fid, '#884400')
                    self.pitfall_t = self.pitfall_cd
                    if self.expiry_t is not None:   # deployed mine → self-destruct
                        self.dead = True
                        return

        # Bloodstone: consistent single-target DoT on one enemy
        if self.bloodstone:
            self.cd -= dt
            if self.cd <= 0:
                self.cd = self.atk_spd
                # Reacquire target if needed
                if (self.bs_target is None or self.bs_target.dead
                        or self.bs_target.hp <= 0 or self.bs_target.fid == self.fid):
                    self.bs_target = None
                    for e in sim.grid.query(self.x, self.y, self.rng):
                        if e.fid != self.fid and not e.dead and e.type in ('unit', 'titan'):
                            if _dist(e.x, e.y, self.x, self.y) <= self.rng:
                                self.bs_target = e
                                break
                if self.bs_target and not self.bs_target.dead:
                    self.bs_target.hp = max(0.0, self.bs_target.hp - self.dmg)
                    self.bs_target.flash = 0.1
                    sim.events.append({'type': 'beam',
                                       'x1': self.x,  'y1': self.y,
                                       'x2': self.bs_target.x, 'y2': self.bs_target.y,
                                       'color': '#CC2222', 'lw': 1.5})

        # Alabaster Angel: kill weakest enemy unit every angel_cd seconds
        if self.btype == 'alabaster_angel' and self.angel_cd > 0:
            self.angel_t -= dt
            if self.angel_t <= 0:
                self.angel_t = self.angel_cd
                tgt = min(
                    (e for e in sim.entities
                     if e.type == 'unit' and e.fid != self.fid and not e.dead),
                    key=lambda e: e.hp, default=None)
                if tgt:
                    sim.events.append({'type': 'beam',
                                       'x1': self.x, 'y1': self.y,
                                       'x2': tgt.x,  'y2': tgt.y,
                                       'color': '#FFFFFF', 'lw': 4})
                    sim.events.append({'type': 'boom', 'x': tgt.x, 'y': tgt.y,
                                       'r': 20, 'color': '#FFFFFF'})
                    tgt.hp   = 0
                    tgt.dead = True

        # Shooting buildings (standard, arcane, cone)
        if self.rng and self.dmg and not self.bloodstone and not self.pitfall:
            self.cd -= dt
            if self.cd <= 0:
                if self.arcane_turret:
                    self._shoot_arcane(sim)
                elif self.cone_aoe:
                    self._shoot_cone(sim)
                else:
                    self._shoot(sim)

        # Church / Beacon AoE heal — units ONLY (bug #5 fix: no buildings/castles)
        if self.btype in ('church', 'beacon') and self.heal_r:
            self.heal_t -= dt
            if self.heal_t <= 0:
                self.heal_t = self.heal_cd
                for e in sim.grid.query(self.x, self.y, self.heal_r):
                    if (e.type == 'unit' and e.fid == self.fid and not e.dead
                            and _dist(e.x, e.y, self.x, self.y) <= self.heal_r
                            and e.hp < e.max_hp):
                        e.hp = min(e.max_hp, e.hp + self.heal_rate * self.heal_cd)
                        e.healing = 0.6

        # Forest zone: stealth, untargetability, enemy slow
        if self.btype == 'forest' and self.zone_r:
            self.zone_t += dt
            if self.zone_t >= 0.5:
                self.zone_t = 0.0
                for e in sim.grid.query(self.x, self.y, self.zone_r + 20):
                    if e.dead:
                        continue
                    d = _dist(e.x, e.y, self.x, self.y)
                    if e.fid == self.fid:
                        in_zone = d <= self.zone_r
                        if in_zone and hasattr(e, 'utype') and e.utype == 'elf_rogue' and not e.stealthed:
                            e.stealthed = True
                        if hasattr(e, 'forest_cover'):
                            e.forest_cover = in_zone
                    elif hasattr(e, 'forest_slow'):
                        e.forest_slow = 0.55 if d <= self.zone_r else 1.0

        if self.bramble_cd > 0:
            self.bramble_cd -= dt

    # ── Shoot helpers ─────────────────────────────────────────────────────────

    def _nearest_shootable(self, sim, exclude_types=('castle', 'building', 'tower')):
        """Find nearest enemy within self.rng, optionally excluding entity types."""
        tgt, bd = None, self.rng
        for e in sim.grid.query(self.x, self.y, self.rng):
            if e.fid == self.fid or e.dead:
                continue
            if exclude_types and e.type in exclude_types:
                continue
            d = _dist(e.x, e.y, self.x, self.y)
            if d < bd:
                bd, tgt = d, e
        return tgt

    def _apply_shot_effects(self, tgt, dmg, sim):
        """Apply on-hit effects common to _shoot and _shoot_arcane."""
        if self.frost_slow:
            tgt.frost_slow = 0.4
            tgt.frost_t    = 2.5
        if self.confuses and random.random() < 0.5:
            tgt.confused  = True
            tgt.confuse_t = 3.0
        if self.raise_dead and tgt.hp <= 0:
            sim.entities.append(Unit(tgt.x, tgt.y, self.fid, 'crypt_skeleton', sim))

    def _shoot(self, sim):
        tgt = None
        bd  = self.rng
        for e in sim.grid.query(self.x, self.y, self.rng):
            if e.fid == self.fid or e.dead:
                continue
            d = _dist(e.x, e.y, self.x, self.y)
            if d < bd:
                bd, tgt = d, e
        if not tgt:
            self.cd = 0.8
            return
        dmg    = self.dmg + (random.random() - 0.5) * 6
        fcolor = sim.factions.get(self.fid, {}).get('color', '#888')
        if tgt.type == 'castle':
            tgt.take_damage(dmg * 0.2, self.fid)
        elif tgt.type in ('tower', 'building'):
            tgt.take_damage(dmg * 0.5, self.fid)
        else:
            tgt.hp = max(0.0, tgt.hp - dmg)
            tgt.flash = 0.15
            if hasattr(tgt, 'combat_t'):
                tgt.combat_t = 0.0
            self._apply_shot_effects(tgt, dmg, sim)
        sim.events.append({'type': 'beam', 'x1': self.x, 'y1': self.y,
                           'x2': tgt.x, 'y2': tgt.y, 'color': fcolor, 'lw': 2})
        if self.aoe:
            _aoe_hit(sim, tgt.x, tgt.y, self.aoe, dmg * 0.4, self.fid, fcolor, exclude=tgt)
        if self.chains:
            hits, prev = [tgt], tgt
            for _ in range(self.chains):
                prev = _chain_hit(sim, hits, prev, dmg, self.fid)
                if prev is None:
                    break
        self.cd = self.atk_spd

    def _shoot_arcane(self, sim):
        """Randomly fires frost bolt (slow) or fire bolt (DoT). Targets units only."""
        tgt = self._nearest_shootable(sim, exclude_types=('castle', 'building', 'tower', 'titan'))
        if not tgt:
            self.cd = 0.8
            return
        dmg = self.dmg + (random.random() - 0.5) * 6
        tgt.hp = max(0.0, tgt.hp - dmg)
        tgt.flash = 0.18
        if hasattr(tgt, 'combat_t'):
            tgt.combat_t = 0.0
        if random.random() < 0.5:
            tgt.frost_slow = 0.4
            tgt.frost_t    = 2.5
            sim.events.append({'type': 'beam', 'x1': self.x, 'y1': self.y,
                               'x2': tgt.x, 'y2': tgt.y, 'color': '#88CCFF', 'lw': 2.5})
        else:
            _apply_dot(tgt, 5, 3.0, 'arcane_fire')
            sim.events.append({'type': 'beam', 'x1': self.x, 'y1': self.y,
                               'x2': tgt.x, 'y2': tgt.y, 'color': '#FF6622', 'lw': 2.5})
        self.cd = self.atk_spd

    def _shoot_cone(self, sim):
        """Flamethrower: 70° cone AoE toward nearest enemy."""
        tgt = self._nearest_shootable(sim, exclude_types=('building', 'tower', 'castle'))
        if not tgt:
            self.cd = 1.0
            return
        aim_ang = math.atan2(tgt.y - self.y, tgt.x - self.x)
        half    = math.radians(35)
        dmg     = self.dmg + (random.random() - 0.5) * 4
        for e in sim.grid.query(self.x, self.y, self.rng):
            if e.fid == self.fid or e.dead or e.type not in ('unit', 'titan'):
                continue
            if _dist(e.x, e.y, self.x, self.y) > self.rng:
                continue
            ang  = math.atan2(e.y - self.y, e.x - self.x)
            diff = abs(math.atan2(math.sin(ang - aim_ang), math.cos(ang - aim_ang)))
            if diff <= half:
                e.hp = max(0.0, e.hp - dmg)
                e.flash = 0.15
                _apply_dot(e, 4, 2.0, 'flamethrower')
        sim.events.append({'type': 'boom',
                           'x': self.x + math.cos(aim_ang) * self.rng * 0.5,
                           'y': self.y + math.sin(aim_ang) * self.rng * 0.5,
                           'r': self.rng * 0.6, 'color': '#FF6600'})
        self.cd = self.atk_spd

    # ── Damage reception ─────────────────────────────────────────────────────

    def take_damage(self, d, attacker_fid):
        self.hp = max(0.0, self.hp - d)
        self.flash = 0.18
        # Bramble Patch retaliates AoE when struck
        if self.bramble and d > 0 and self.bramble_cd <= 0 and self._sim_ref is not None:
            self.bramble_cd = 0.5
            _aoe_hit(self._sim_ref, self.x, self.y, 55, 18, self.fid, '#44AA22')
        if self.hp <= 0:
            self.dead = True

    def to_dict(self):
        return {'id': self.id, 'type': 'building', 'fid': self.fid, 'btype': self.btype,
                'x': self.x, 'y': self.y, 'hp': self.hp, 'max_hp': self.max_hp,
                'flash': self.flash, 'aoe': self.aoe}


# ─── Castle ───────────────────────────────────────────────────────────────────

_HORSEMAN_ORDER = ('pestilence', 'war_horseman', 'famine', 'death_horseman')


class Castle:
    def __init__(self, x, y, fid):
        self.id       = _new_id()
        self.x, self.y = x, y
        self.fid      = fid
        self.type     = 'castle'
        self.hp       = self.max_hp = 1600.0
        self.gold     = 120.0
        self.dead     = False
        self.flash    = 0.0
        self.spawn_t  = 1.0 + random.random() * 2
        self.build_cd = 0.0
        self.swarm_state   = 'gathering'
        self.swarm_target  = None
        self.swarm_check_t = 0.0
        self.desperation_active   = False
        self.desperation_cooldown = 0.0

    def update(self, dt, sim):
        self.gold    += PASSIVE_GOLD * dt
        self.spawn_t -= dt
        self.build_cd = max(0.0, self.build_cd - dt)

        if self.desperation_cooldown > 0:
            self.desperation_cooldown -= dt
        elif not self.desperation_active and self.hp / self.max_hp < 0.28:
            self.desperation_active = True

        if self.desperation_active:
            self.hp = min(self.max_hp * 0.40, self.hp + 7 * dt)
            if self.hp / self.max_hp >= 0.40:
                self.desperation_active   = False
                self.desperation_cooldown = 120.0
                sim.events.append({'type': 'sparks', 'x': self.x, 'y': self.y,
                                   'color': sim.factions.get(self.fid, {}).get('hi', '#FFFFFF'),
                                   'n': 10})

        if self.spawn_t <= 0:
            self._try_spawn(sim)
            base = FACTION_SPAWN_INTERVAL.get(self.fid, 1.8)
            self.spawn_t = base + random.random() * 0.9

        if self.fid == 'red':
            self.swarm_check_t -= dt
            if self.swarm_check_t <= 0:
                self.swarm_check_t = 2.0
                self._update_swarm(sim)

    def _update_swarm(self, sim):
        swarms = [e for e in sim.entities
                  if e.fid == 'red' and e.type == 'unit'
                  and e.utype == 'hive_swarm' and not e.dead]
        if self.swarm_state == 'gathering':
            if len(swarms) >= SWARM_THRESHOLD:
                weak = min(
                    (e for e in sim.entities
                     if e.type == 'castle' and e.fid != 'red' and not e.dead),
                    key=lambda e: e.hp, default=None)
                if weak:
                    self.swarm_state  = 'rushing'
                    self.swarm_target = weak.fid
                    for s in swarms:
                        s.swarm_rushing    = True
                        s.swarm_target_fid = weak.fid
        else:
            if self.swarm_target not in sim.castle_cache or \
               sum(1 for s in swarms if s.swarm_rushing) < 3:
                self.swarm_state  = 'gathering'
                self.swarm_target = None
                for s in swarms:
                    s.swarm_rushing    = False
                    s.swarm_target_fid = None

    def _try_spawn(self, sim):
        f        = self.fid
        bldg_cfg = FBLDG.get(f)
        if not bldg_cfg:
            return
        cap = FACTION_UNIT_CAPS.get(f, MAX_UNITS_PER_FACTION)
        if sim.faction_unit_count.get(f, 0) >= cap:
            return

        inc_count = sim.faction_inc_bldg_count.get(f, 0)
        def_count = sim.faction_def_bldg_count.get(f, 0)
        sp_count  = sim.faction_sp_bldg_count.get(f, 0)

        builder_type = bldg_cfg.get('builder', f + '_builder')
        # Use cached builder flag — avoids O(n) entity scan every spawn tick
        has_builder  = sim.faction_has_builder.get(f, False)

        if not has_builder and self.gold >= 30 and self.build_cd <= 0:
            if inc_count < MAX_INC_BLDG:
                return self._spawn_builder(builder_type, bldg_cfg['income'], sim)
            if def_count < MAX_DEF_BLDG and random.random() < 0.5:
                return self._spawn_builder(builder_type, bldg_cfg['defense'], sim)
            if bldg_cfg.get('special') and sp_count < MAX_SPECIAL and random.random() < 0.3:
                return self._spawn_builder(builder_type, bldg_cfg['special'], sim)

        # Unit spawning
        pool  = SPAWN_POOLS.get(f, ['hive_soldier'])
        utype = self._pick_unit(f, pool, sim)
        if utype is None:
            return
        cost = UTYPES.get(utype, {}).get('cost', 40)
        if self.gold >= cost:
            self.gold -= cost
            sim.entities.append(Unit(
                self.x + random.uniform(-17, 17),
                self.y + random.uniform(-17, 17),
                f, utype, sim))

    def _pick_unit(self, f, pool, sim):
        """Return the utype to spawn, enforcing faction-specific gates.
        Returns None if no unit should be spawned this tick.
        Gold deduction is always handled by the caller (_try_spawn).
        """
        if f == 'apoc':
            return self._apoc_next_unit(sim)
        utype = random.choice(pool)
        if f == 'dagon' and utype == 'elder_god':
            # Gate: need 50 cultists on the field before elder god is purchasable
            if sim.faction_cultist_count.get(f, 0) < 50:
                utype = 'cultist'
        return utype

    def _apoc_next_unit(self, sim):
        """Return the next purchasable Horseman utype in sequence, or None.

        Bug fix: previously deducted gold here AND returned None, so the unit
        was never spawned. Now returns the utype string; _try_spawn handles
        the actual gold deduction and entity creation.
        """
        ever_bought = sim.faction_horseman_ever_bought.get(self.fid, set())
        alive       = {e.utype for e in sim.entities
                       if e.fid == self.fid and e.type == 'unit'
                       and getattr(e, 'is_horseman', False) and not e.dead}

        for i, utype in enumerate(_HORSEMAN_ORDER):
            if utype in alive:
                continue   # this horseman is already on the field; try next
            # Prerequisite: every predecessor must have been purchased at some point
            if i > 0 and _HORSEMAN_ORDER[i - 1] not in ever_bought:
                return None   # sequence gate not met
            # Record purchase intent before gold is deducted so the gate opens
            # for the next horseman on a future tick
            sim.faction_horseman_ever_bought.setdefault(self.fid, set()).add(utype)
            return utype   # caller will check gold and spawn the unit

        return None   # all four horsemen alive or sequence exhausted

    def _spawn_builder(self, utype, btype, sim):
        if utype not in UTYPES:
            return
        cost = UTYPES[utype].get('cost', 30)
        if self.gold < cost:
            return
        self.gold    -= cost
        self.build_cd = 40.0
        u = Unit(self.x + random.uniform(-12, 12),
                 self.y + random.uniform(-12, 12),
                 self.fid, utype, sim)
        u.assigned_btype = btype
        sim.entities.append(u)

    def take_damage(self, d, _fid):
        self.hp = max(0.0, self.hp - d)
        if self.hp <= 0:
            self.dead = True

    def to_dict(self):
        return {'id': self.id, 'type': 'castle', 'fid': self.fid,
                'x': self.x, 'y': self.y, 'hp': self.hp, 'max_hp': self.max_hp,
                'gold': self.gold, 'flash': self.flash,
                'desperation_active':   self.desperation_active,
                'desperation_cooldown': self.desperation_cooldown}


# ─── Unit ─────────────────────────────────────────────────────────────────────

_UNDEAD_TYPES  = frozenset({'zombie', 'crypt_skeleton', 'crypt_archer',
                             'bone_death_knight', 'lich', 'dominus_mortus'})
_CHOIR_AURA_R  = 90.0
_CHOIR_AURA_DT = 0.5    # seconds between aura pulses
_MAN_SYNERGY_R = 80.0   # Empire of Man proximity radius


class Unit:
    def __init__(self, x, y, fid, utype, sim):
        self.id      = _new_id()
        self.x, self.y = x, y
        self.fid     = fid
        self.utype   = utype
        self.type    = 'unit'
        s = UTYPES.get(utype, {'hp': 30, 'dmg': 8, 'spd': 40,
                                'rng': 22, 'atk_spd': 1.5, 'size': 5, 'cost': 30})

        # ── Test Subject: randomised stats scaled by Lab count ─────────────────
        if s.get('is_test_subject') and sim is not None:
            lab_n = sim.faction_lab_count.get(fid, 0)
            rb    = lab_n * 10
            self.hp = self.max_hp = float(max(10, random.randint(
                max(10, 30 - rb), 120 + rb)))
            self.dmg     = float(random.randint(max(2, 5 - lab_n), 35 + rb))
            self.spd     = float(random.randint(max(10, 18 - rb // 2), 60 + rb // 2))
            self.atk_spd = round(random.uniform(max(0.4, 0.8 - lab_n * 0.05), 2.5), 2)
            self.armor   = round(random.uniform(0.0, min(0.5, lab_n * 0.05)), 2)
        else:
            self.hp = self.max_hp = float(s.get('hp', 30))
            self.dmg     = float(s.get('dmg', 8))
            self.spd     = float(s.get('spd', 40))
            self.atk_spd = float(s.get('atk_spd', 1.5))
            self.armor   = float(s.get('armor', 0.0))

        self.rng       = float(s.get('rng', 22))
        self.size      = s.get('size', 5)
        self.aoe       = float(s.get('aoe', 0))
        self.chains    = s.get('chains', 0)
        self.heal      = float(s.get('heal', 0))
        self.burst_dmg = float(s.get('burst_dmg', 0))

        # Boolean flags — pulled once from UTYPES so per-tick access is O(1)
        self.is_bomber        = s.get('is_bomber',        False)
        self.is_builder       = s.get('is_builder',       False)
        self.is_bastion_builder=s.get('is_bastion_builder',False)
        self.build_time       = s.get('build_time',       10)
        self.assigned_btype   = s.get('b_type',           None)
        self.spawns           = s.get('spawns',           None)
        self.summons          = s.get('summons',          None)
        self.no_regen         = s.get('no_regen',         False)
        self.river_bonus      = s.get('river_bonus',      False)
        self.poison_on_hit    = s.get('poison_on_hit',    False)
        self.frost_slow_atk   = s.get('frost_slow',       False)
        self.confuses         = s.get('confuses',         False)
        self.raise_dead       = s.get('raise_dead',       False)
        self.heal_on_kill     = s.get('heal_on_kill',     False)
        self.blood_rage       = s.get('blood_rage',       False)
        self.charge_dmg       = s.get('charge_dmg',       False)
        self.burn_aura        = s.get('burn_aura',        False)
        self.fire_dot         = s.get('fire_dot',         False)
        self.plague_dot       = s.get('plague_dot',       False)
        self.is_sporomancer   = s.get('is_sporomancer',   False)
        self.is_elder_god     = s.get('is_elder_god',     False)
        self.is_dominus       = s.get('is_dominus',       False)
        self.is_cult_leader   = s.get('is_cult_leader',   False)
        self.is_crypt_unit    = s.get('is_crypt_unit',    False)
        self.is_engineer      = s.get('is_engineer',      False)
        self.is_sapper        = s.get('is_sapper',        False)
        self.is_craftsman     = s.get('is_craftsman',     False)
        self.is_clockwork     = s.get('is_clockwork',     False)
        self.is_blood_knight  = s.get('is_blood_knight',  False)
        self.is_blood_mage    = s.get('is_blood_mage',    False)
        self.is_hoplite       = s.get('is_hoplite',       False)
        self.is_mann_archer   = s.get('is_mann_archer',   False)
        self.is_bard          = s.get('is_bard',          False)
        self.is_famine        = s.get('is_famine',        False)
        self.choir_aura       = s.get('choir_aura',       None)
        self.death_spawn      = s.get('death_spawn',      None)
        self.goblin_debuff    = s.get('goblin_debuff',    False)
        self.is_horseman      = s.get('is_horseman',      False)
        self.horseman_idx     = s.get('horseman_idx',     -1)

        # Runtime state
        self.dead           = False
        self.flash          = 0.0
        self.facing         = 1
        self.wob            = random.random() * math.pi * 2
        self.cd             = random.random() * self.atk_spd
        self.combat_t       = 0.0
        self.healing        = 0.0
        self.stealthed      = utype in ('elf_rogue', 'phantom')
        self.stealth_rev_t  = 0.0
        self.forest_cover   = False
        self.forest_slow    = 1.0
        self.build_target   = None
        self.build_progress = 0.0
        self.my_minions     = []
        self.necro_t        = 0.0
        self.summoner_ref   = None
        self.home_building  = None
        self.swarm_rushing  = False
        self.swarm_target_fid = None
        self.dots           = []
        self.frost_t        = 0.0
        self.frost_slow     = 1.0
        self.confused       = False
        self.confuse_t      = 0.0
        self._locked_target = None
        self.prev_x, self.prev_y = x, y
        self.moved_dist     = 0.0
        self._sim           = sim
        self.controlled_target   = None
        self.control_cd          = 0.0
        self.engineer_cd    = random.uniform(8, 14)
        self.wall_mounted   = False
        self.aura_t         = 0.0
        self.dominus_check_t = 0.0
        self.choir_aura_t   = random.random() * _CHOIR_AURA_DT
        self.shield_hp      = 0.0
        self.craftsman_minions = []
        self.famine_t       = 0.0

        # Apply spawn-time HP bonuses
        if sim is not None:
            self._apply_spawn_bonuses(sim, fid)

    def _apply_spawn_bonuses(self, sim, fid):
        """One place for all faction spawn-time stat multipliers."""
        mult = 1.0
        mine_n   = sim.faction_mine_count.get(fid, 0)
        fount_n  = sim.faction_blood_fountain_count.get(fid, 0)
        amp_n    = sim.faction_amphitheater_count.get(fid, 0)
        if mine_n  > 0:
            mult *= 1.0 + 0.05 * mine_n
        if fount_n > 0:
            mult *= 1.0 + 0.10 * fount_n
        if mult != 1.0:
            self.hp = self.max_hp = self.max_hp * mult
        # Choir units: amphitheater boosts dmg, hp, spd at spawn
        if amp_n > 0 and self.choir_aura:
            am = 1.0 + 0.01 * amp_n
            self.dmg     *= am
            self.hp       = self.max_hp = self.max_hp * am
            self.spd     *= am

    def _dist(self, o):
        return _dist(self.x, self.y, o.x, o.y)

    # ── Main update ───────────────────────────────────────────────────────────

    def update(self, dt, sim):
        if self.hp <= 0:
            self._on_death(sim)
            self.dead = True
            return

        self.cd     -= dt
        self.flash   = max(0.0, self.flash - dt)
        self.healing = max(0.0, self.healing - dt)
        self.wob    += dt * 1.7

        # Shield decay
        if self.shield_hp > 0:
            self.shield_hp = max(0.0, self.shield_hp - dt * 2)

        # DoTs
        for dot in self.dots:
            self.hp  -= dot['dmg'] * dt
            dot['t'] -= dt
        self.dots = [d for d in self.dots if d['t'] > 0]
        if self.hp <= 0:
            self._on_death(sim)
            self.dead = True
            return

        # Status timers
        if self.frost_t > 0:
            self.frost_t -= dt
            if self.frost_t <= 0:
                self.frost_slow = 1.0
        if self.confuse_t > 0:
            self.confuse_t -= dt
            if self.confuse_t <= 0:
                self.confused = False
        if self.utype in ('elf_rogue', 'phantom') and not self.stealthed and self.stealth_rev_t > 0:
            self.stealth_rev_t -= dt
            if self.stealth_rev_t <= 0:
                self.stealthed = True

        # Library attack-speed buff (Arcane Academy)
        if self.fid == 'blue':
            lib_n = sim.faction_lib_count.get('blue', 0)
            if lib_n:
                self.cd -= dt * 0.05 * lib_n

        # Combat regen (red Hive)
        if self.fid == 'red' and not self.no_regen and self.hp < self.max_hp:
            self.combat_t += dt
            if self.combat_t > 2.4:
                self.hp = min(self.max_hp, self.hp + 11 * dt)

        if self.charge_dmg:
            self.moved_dist = self.moved_dist * 0.92 + _dist(
                self.x, self.y, self.prev_x, self.prev_y)
        self.prev_x, self.prev_y = self.x, self.y

        if sim.mania_t > 0:
            return

        sp_mult = self._speed_mult(sim)

        # ── Choir aura pulses ─────────────────────────────────────────────────
        if self.choir_aura:
            self.choir_aura_t -= dt
            if self.choir_aura_t <= 0:
                self.choir_aura_t = _CHOIR_AURA_DT
                self._apply_choir_aura(sim)

        # ── Empire of Man proximity synergies ─────────────────────────────────
        if self.is_hoplite:
            nearby = sum(1 for e in sim.grid.query(self.x, self.y, _MAN_SYNERGY_R)
                         if e is not self and e.fid == self.fid
                         and e.utype == 'hoplite' and not e.dead
                         and _dist(e.x, e.y, self.x, self.y) <= _MAN_SYNERGY_R)
            self.armor = min(0.60, 0.08 * nearby)

        if self.is_mann_archer:
            nearby = sum(1 for e in sim.grid.query(self.x, self.y, _MAN_SYNERGY_R)
                         if e is not self and e.fid == self.fid
                         and e.utype == 'mann_archer' and not e.dead
                         and _dist(e.x, e.y, self.x, self.y) <= _MAN_SYNERGY_R)
            self.atk_spd = max(0.5, UTYPES['mann_archer']['atk_spd'] * (1.0 - 0.12 * nearby))

        if self.is_bard:
            self.aura_t -= dt
            if self.aura_t <= 0:
                self.aura_t = _CHOIR_AURA_DT
                nearby_bards = sum(1 for e in sim.grid.query(self.x, self.y, _MAN_SYNERGY_R)
                                   if e is not self and e.fid == self.fid
                                   and e.utype == 'bard' and not e.dead
                                   and _dist(e.x, e.y, self.x, self.y) <= _MAN_SYNERGY_R)
                sv = 10.0 + 8.0 * nearby_bards
                for e in sim.grid.query(self.x, self.y, _MAN_SYNERGY_R):
                    if e.fid == self.fid and e.type == 'unit' and not e.dead:
                        if _dist(e.x, e.y, self.x, self.y) <= _MAN_SYNERGY_R:
                            e.shield_hp = min(e.max_hp * 0.5, e.shield_hp + sv)

        # ── Famine aura ───────────────────────────────────────────────────────
        if self.is_famine:
            self.famine_t -= dt
            if self.famine_t <= 0:
                self.famine_t = 1.0
                for e in sim.grid.query(self.x, self.y, 100):
                    if e.fid != self.fid and not e.dead and e.type == 'unit':
                        if _dist(e.x, e.y, self.x, self.y) <= 100:
                            e.dmg = max(1.0, e.dmg * 0.95)

        # ── Craftsman: manage clockwork minions ───────────────────────────────
        if self.is_craftsman:
            self.craftsman_minions = [m for m in self.craftsman_minions
                                      if not m.dead and m.hp > 0]
            if len(self.craftsman_minions) < 3:
                self.necro_t += dt
                if self.necro_t >= 10.0:
                    self.necro_t = 0.0
                    cw = Unit(self.x + random.uniform(-10, 10),
                              self.y + random.uniform(-10, 10),
                              self.fid, 'clockwork', sim)
                    cw.summoner_ref = self
                    sim.entities.append(cw)
                    self.craftsman_minions.append(cw)

        # ── Necro summon loop ─────────────────────────────────────────────────
        if self.summons:
            self.my_minions = [m for m in self.my_minions if not m.dead and m.hp > 0]
            if len(self.my_minions) < 3:
                self.necro_t += dt
                if self.necro_t >= 8.0:
                    self._summon(sim, self.summons)
                    self.necro_t = 0.0

        # ── Undead bodyguard AI ───────────────────────────────────────────────
        if self.utype in ('crypt_skeleton', 'zombie', 'crypt_archer') and self.summoner_ref:
            self._bodyguard_ai(dt, sp_mult, sim)
            return

        if self.is_crypt_unit and self.home_building and not self.home_building.dead:
            self._brood_bug_ai(dt, sp_mult, sim)
            return

        if self.spawns and self.cd <= 0:
            sim.entities.append(Unit(self.x, self.y, self.fid, self.spawns, sim))
            self.cd = self.atk_spd

        # ── Builder / special AIs ─────────────────────────────────────────────
        if self.is_bastion_builder:
            self._do_bastion_build(dt, sp_mult, sim)
        elif self.is_builder:
            self._do_build(dt, sp_mult, sim)
        elif self.is_engineer:
            self._do_engineer(dt, sp_mult, sim)
        elif self.utype == 'brood_bug' and self.home_building and not self.home_building.dead:
            self._brood_bug_ai(dt, sp_mult, sim)
        elif self.utype == 'hive_swarm':
            self._swarm_ai(dt, sp_mult, sim)
        elif self.is_sporomancer:
            self._sporomancer_ai(dt, sp_mult, sim)
        elif self.is_elder_god:
            self._elder_god_ai(dt, sp_mult, sim)
        elif self.is_dominus:
            self._dominus_ai(dt, sp_mult, sim)
        elif self.is_blood_mage:
            self._blood_mage_ai(dt, sp_mult, sim)
        elif self.is_cult_leader:
            self._cult_leader_ai(dt, sp_mult, sim)
        else:
            self._combat_ai(dt, sp_mult, sim)

    # ── Speed multiplier ─────────────────────────────────────────────────────

    def _speed_mult(self, sim):
        m = self.forest_slow
        if sim.blizzard_t > 0:
            m *= 0.28
        if self.frost_t > 0:
            m *= 0.6
        castle = sim.castle_cache.get(self.fid)
        if castle and castle.desperation_active:
            m *= 1.25
        if self.fid == 'red':
            for tmr in sim.tumor_list:
                if _dist(self.x, self.y, tmr.x, tmr.y) < tmr.aoe_spd_r:
                    m = max(m, 1.5)
                    break
        return m

    # ── Death callback ────────────────────────────────────────────────────────

    def _on_death(self, sim):
        # on-death unit spawn (wolf_rider → goblin, etc.)
        if self.death_spawn:
            u = Unit(self.x + random.uniform(-8, 8),
                     self.y + random.uniform(-8, 8),
                     self.fid, self.death_spawn, sim)
            sim.entities.append(u)
            sim.events.append({'type': 'sparks', 'x': self.x, 'y': self.y,
                               'color': '#44AA44', 'n': 5})

        # Horseman death → builder starts a cairn
        if self.is_horseman:
            b = Unit(self.x, self.y, self.fid, 'apoc_builder', sim)
            b.assigned_btype = 'cairn'
            sim.entities.append(b)

        # Plague DoT spread on death (40% chance per nearby enemy)
        if any(d.get('src') == 'plague_spread' for d in self.dots):
            if random.random() < 0.40:
                for e in sim.grid.query(self.x, self.y, 80):
                    if e is self or e.dead or e.fid == self.fid or e.type != 'unit':
                        continue
                    if _dist(e.x, e.y, self.x, self.y) < 80:
                        _apply_dot(e, 5, 20.0, 'plague_spread')
                        sim.events.append({'type': 'sparks', 'x': e.x, 'y': e.y,
                                           'color': '#AA44AA', 'n': 4})

        # Fungal Patch mushling respawn (10% per nearby patch)
        if self.utype == 'mushling' and sim is not None:
            for b in sim.grid.query(self.x, self.y, 120):
                if (b.type == 'building' and b.btype == 'fungal_patch'
                        and b.fid == self.fid and not b.dead
                        and _dist(self.x, self.y, b.x, b.y) < 120):
                    if random.random() < 0.10:
                        ang = random.random() * math.pi * 2
                        sim.entities.append(Unit(
                            b.x + math.cos(ang) * 30,
                            b.y + math.sin(ang) * 30,
                            self.fid, 'mushling', sim))
                        sim.events.append({'type': 'sparks', 'x': b.x, 'y': b.y,
                                           'color': '#88AA22', 'n': 4})
                    break

    # ── Choir aura ────────────────────────────────────────────────────────────

    def _apply_choir_aura(self, sim):
        amp_n   = sim.faction_amphitheater_count.get(self.fid, 0)
        bonus   = 1.0 + 0.01 * amp_n
        aura    = self.choir_aura
        for e in sim.grid.query(self.x, self.y, _CHOIR_AURA_R):
            if e is self or e.fid != self.fid or e.dead or e.type != 'unit':
                continue
            if _dist(e.x, e.y, self.x, self.y) > _CHOIR_AURA_R:
                continue
            if aura == 'dmg':
                cap = UTYPES.get(e.utype, {}).get('dmg', e.dmg) * 2.5
                e.dmg = min(cap, e.dmg * (1.0 + 0.05 * bonus))
            elif aura == 'hp':
                heal = 4.0 * bonus
                e.hp = min(e.max_hp, e.hp + heal)
                e.healing = 0.4
            elif aura == 'atk_spd':
                base = UTYPES.get(e.utype, {}).get('atk_spd', e.atk_spd)
                e.atk_spd = max(0.3, base * (1.0 - 0.08 * bonus))
            elif aura == 'heal':
                e.hp = min(e.max_hp, e.hp + 3.0 * bonus)
                e.healing = 0.3
            elif aura == 'aoe':
                base = UTYPES.get(e.utype, {}).get('aoe', 0)
                e.aoe = max(e.aoe, base + 15.0 * bonus)
            elif aura == 'rng':
                base = UTYPES.get(e.utype, {}).get('rng', e.rng)
                e.rng = min(base * 1.4, e.rng + 10.0 * bonus)
            # 'spd' aura just removes slows — handled by not clamping forest_slow below 1

    # ── Special unit AIs ─────────────────────────────────────────────────────

    def _bodyguard_ai(self, dt, sp_mult, sim):
        """Undead minion guards its summoner, intercepting nearby threats."""
        sm = self.summoner_ref
        if not sm or sm.dead or sm.hp <= 0:
            self.hp = 0
            self.dead = True
            return
        threat, td = None, 200.0
        for e in sim.grid.query(sm.x, sm.y, 200):
            if e.fid == self.fid or e.dead:
                continue
            d = _dist(e.x, e.y, sm.x, sm.y)
            if d < td:
                td, threat = d, e
        if threat:
            ang = math.atan2(threat.y - sm.y, threat.x - sm.x)
            self._move_to(sm.x + math.cos(ang) * 30, sm.y + math.sin(ang) * 30, dt, 1.0, sim)
            self.facing = 1 if threat.x > self.x else -1
            if self._dist(threat) <= self.rng and self.cd <= 0:
                self.cd = self.atk_spd
                self._deal_dmg(threat, self.dmg, sim)
        else:
            oa = self.wob * 0.4
            self._move_to(sm.x + math.cos(oa) * 28, sm.y + math.sin(oa) * 28, dt, 1.0, sim)

    def _cult_leader_ai(self, dt, sp_mult, sim):
        """Buffs nearby cultists then proceeds with normal combat."""
        self.aura_t -= dt
        if self.aura_t <= 0:
            self.aura_t = 1.0
            base_dmg = UTYPES['cultist']['dmg']
            base_as  = UTYPES['cultist']['atk_spd']
            for e in sim.grid.query(self.x, self.y, 100):
                if e.fid == self.fid and e.type == 'unit' and e.utype == 'cultist' and not e.dead:
                    if _dist(e.x, e.y, self.x, self.y) < 100:
                        e.dmg     = base_dmg * 1.5
                        e.atk_spd = base_as  * 0.75
        self._combat_ai(dt, sp_mult, sim)

    def _sporomancer_ai(self, dt, sp_mult, sim):
        """Mind-controls one enemy unit; controlled unit degrades over time."""
        self.control_cd = max(0.0, self.control_cd - dt)
        ct = self.controlled_target
        if ct is not None:
            if ct.dead or ct.hp <= 0:
                self.controlled_target = None
            else:
                ct.hp     = max(0.0, ct.hp - 4.0 * dt)
                ct.max_hp = max(1.0, ct.max_hp - ct.max_hp * 0.02 * dt)
                ct.confused  = True
                ct.confuse_t = 0.5
        if self.controlled_target is None and self.control_cd <= 0:
            for e in sim.grid.query(self.x, self.y, self.rng):
                if e.fid != self.fid and not e.dead and e.type == 'unit':
                    if _dist(e.x, e.y, self.x, self.y) <= self.rng:
                        self.controlled_target = e
                        self.control_cd = 20.0
                        sim.events.append({'type': 'beam',
                                           'x1': self.x, 'y1': self.y,
                                           'x2': e.x,    'y2': e.y,
                                           'color': '#AAFF44', 'lw': 2})
                        break
        self._combat_ai(dt, sp_mult, sim)

    def _elder_god_ai(self, dt, sp_mult, sim):
        """Periodically sacrifices nearby cultists to heal."""
        self.control_cd = max(0.0, self.control_cd - dt)
        if self.control_cd <= 0 and self.hp < self.max_hp:
            altar_n = sim.faction_altar_count.get(self.fid, 0)
            cost    = max(5, 10 - altar_n * 2)
            nearby  = [e for e in sim.grid.query(self.x, self.y, 120)
                       if e.fid == self.fid and e.type == 'unit'
                       and e.utype == 'cultist' and not e.dead
                       and _dist(e.x, e.y, self.x, self.y) < 120]
            if len(nearby) >= cost:
                for c in nearby[:cost]:
                    c.hp = 0
                    c.dead = True
                self.hp = min(self.max_hp, self.hp + 80.0 * cost)
                self.healing    = 1.5
                self.control_cd = 6.0
                sim.events.append({'type': 'boom', 'x': self.x, 'y': self.y,
                                   'r': 40, 'color': '#6644AA'})
            else:
                self.control_cd = 2.0
        self._combat_ai(dt, sp_mult, sim)

    def _dominus_ai(self, dt, _sp_mult, sim):
        """Waits until 100 undead on field, then sacrifices them to become a death titan."""
        self.dominus_check_t -= dt
        if self.dominus_check_t > 0:
            return
        self.dominus_check_t = 3.0
        undead = [e for e in sim.entities
                  if e.fid == self.fid and e.type == 'unit'
                  and e.utype in _UNDEAD_TYPES and e is not self and not e.dead]
        if len(undead) >= 100:
            for u in undead[:100]:
                u.hp = 0
                u.dead = True
            sim.events.append({'type': 'boom', 'x': self.x, 'y': self.y,
                               'r': 120, 'color': '#C8C080'})
            sim.entities.append(Titan('death_titan', self.x, self.y, self.fid))
            self.hp   = 0
            self.dead = True

    def _blood_mage_ai(self, dt, sp_mult, sim):
        """Siphons HP from target; splits 30% to nearby allies."""
        tgt = self._find_target(sim)
        if tgt and self._dist(tgt) > self.rng:
            wx, wy = get_waypoint(self.x, self.y, tgt.x, tgt.y, sim.rivers, sim.bridges)
            self._move_to(wx, wy, dt, sp_mult, sim)
            return
        if tgt and self.cd <= 0:
            self.cd = self.atk_spd
            drain = self.dmg + random.uniform(-2, 2)
            if tgt.type == 'unit':
                tgt.hp = max(0.0, tgt.hp - drain)
                tgt.flash = 0.15
                self.hp = min(self.max_hp, self.hp + drain * 0.50)
                allies = [e for e in sim.grid.query(self.x, self.y, 100)
                          if e.fid == self.fid and e.type == 'unit'
                          and not e.dead and e is not self
                          and _dist(e.x, e.y, self.x, self.y) <= 100]
                if allies:
                    per = (drain * 0.30) / len(allies)
                    for a in allies:
                        a.hp = min(a.max_hp, a.hp + per)
                        a.healing = 0.4
                sim.events.append({'type': 'beam',
                                   'x1': self.x, 'y1': self.y,
                                   'x2': tgt.x,  'y2': tgt.y,
                                   'color': '#CC2222', 'lw': 2})

    def _do_engineer(self, dt, sp_mult, sim):
        """Places a temporary auto-turret every ~12-18s, then fights normally."""
        self.engineer_cd -= dt
        if self.engineer_cd <= 0:
            self.engineer_cd = random.uniform(12, 18)
            b = Building(self.x + random.uniform(-8, 8),
                         self.y + random.uniform(-8, 8),
                         self.fid, 'btower')
            b.expiry_t  = 30.0
            b._sim_ref  = sim
            b.dmg       = 22.0
            b.rng       = 150.0
            b.atk_spd   = 1.8
            b.cd        = 1.0
            sim.entities.append(b)
            sim.events.append({'type': 'sparks', 'x': self.x, 'y': self.y,
                               'color': sim.factions.get(self.fid, {}).get('hi', '#fff'),
                               'n': 6})
        self._combat_ai(dt, sp_mult, sim)

    def _do_bastion_build(self, dt, sp_mult, sim):
        """Bastion builder: selects and places walls, gates, towers, quarries, or bastilas."""
        if not self.assigned_btype:
            inc  = sim.faction_inc_bldg_count.get(self.fid, 0)
            def_ = sim.faction_def_bldg_count.get(self.fid, 0)
            walls = sum(1 for e in sim.entities
                        if e.type == 'building' and e.fid == self.fid
                        and e.btype in ('bwall', 'bgate'))
            if inc < MAX_INC_BLDG:
                self.assigned_btype = 'quarry'
            elif walls < 4:
                self.assigned_btype = random.choice(['bwall', 'bwall', 'bgate'])
            elif def_ < MAX_DEF_BLDG:
                self.assigned_btype = random.choice(['btower', 'bastila'])
            else:
                self.assigned_btype = 'bwall'

        btype = self.assigned_btype
        if not self.build_target:
            f_data = sim.factions.get(self.fid, {})
            cx, cy = f_data.get('cx', self.x), f_data.get('cy', self.y)
            for _ in range(90):
                if btype in ('bwall', 'bgate'):
                    ang = random.uniform(0, math.pi * 2)
                    r   = random.uniform(80, 150)
                    bx  = cx + math.cos(ang) * r
                    by  = cy + math.sin(ang) * r
                else:
                    bx = cx + random.uniform(-180, 180)
                    by = cy + random.uniform(-180, 180)
                if bx < 24 or bx > MAP_W - 24 or by < 24 or by > MAP_H - 24:
                    continue
                if in_river(bx, by, sim.rivers, sim.bridges):
                    continue
                if any(e.type in ('building', 'castle')
                       and _dist(bx, by, e.x, e.y) < 45
                       for e in sim.entities):
                    continue
                self.build_target = (bx, by)
                break
            if not self.build_target:
                self.build_target = (cx + random.uniform(-80, 80),
                                     cy + random.uniform(-80, 80))

        tx, ty = self.build_target
        if _dist(self.x, self.y, tx, ty) > 7:
            wx, wy = get_waypoint(self.x, self.y, tx, ty, sim.rivers, sim.bridges)
            self._move_to(wx, wy, dt, sp_mult, sim)
        else:
            self.build_progress += dt
            build_time = _BLDG_STATS.get(btype, {}).get('hp', 200) / 30.0
            if self.build_progress >= build_time:
                nb = Building(self.x, self.y, self.fid, btype)
                nb._sim_ref = sim
                q_n = sim.faction_quarry_count.get(self.fid, 0)
                if q_n > 0:
                    nb.hp = nb.max_hp = nb.hp * (1.0 + 0.10 * q_n)
                sim.entities.append(nb)
                sim.events.append({'type': 'sparks', 'x': self.x, 'y': self.y,
                                   'color': sim.factions.get(self.fid, {}).get('hi', '#fff'),
                                   'n': 8})
                self.dead = True

    def _swarm_ai(self, dt, sp_mult, sim):
        if self.swarm_rushing and self.swarm_target_fid:
            tc = sim.castle_cache.get(self.swarm_target_fid)
            if not tc:
                self.swarm_rushing    = False
                self.swarm_target_fid = None
                self._combat_ai(dt, sp_mult, sim)
                return
            if self._dist(tc) > self.rng:
                wx, wy = get_waypoint(self.x, self.y, tc.x, tc.y, sim.rivers, sim.bridges)
                self._move_to(wx, wy, dt, sp_mult * 1.1, sim)
            near = self._nearest_enemy(self.rng + 20, sim)
            if near and self.cd <= 0:
                self._attack(near, sim)
        else:
            home = sim.castle_cache.get(self.fid)
            if not home:
                self._combat_ai(dt, sp_mult, sim)
                return
            if self._dist(home) > 70:
                wx, wy = get_waypoint(self.x, self.y, home.x, home.y, sim.rivers, sim.bridges)
                self._move_to(wx, wy, dt, sp_mult, sim)
            else:
                oa = self.wob * 0.35
                self._move_to(home.x + math.cos(oa) * 55,
                              home.y + math.sin(oa) * 55, dt, sp_mult * 0.6, sim)
                threat = self._nearest_enemy(90, sim)
                if threat and self.cd <= 0:
                    self._attack(threat, sim)

    def _brood_bug_ai(self, dt, sp_mult, sim):
        home   = self.home_building
        threat = self._nearest_enemy(120, sim)
        if threat:
            if self._dist(threat) <= self.rng:
                if self.cd <= 0:
                    self._attack(threat, sim)
            else:
                self._move_to(threat.x, threat.y, dt, sp_mult, sim)
            self.facing = 1 if threat.x > self.x else -1
        elif home and self._dist(home) > 40:
            ang = math.atan2(home.y - self.y, home.x - self.x)
            ts  = terrain_speed(self.x, self.y, sim.rivers, sim.bridges, self.river_bonus)
            self.x += math.cos(ang) * self.spd * sp_mult * ts * dt
            self.y += math.sin(ang) * self.spd * sp_mult * ts * dt

    def _combat_ai(self, dt, sp_mult, sim):
        tgt = self._find_target(sim)
        if not tgt:
            return
        d         = self._dist(tgt)
        is_ranged = self.rng > 40
        eng_r     = self.rng * 0.62 if is_ranged else self.rng

        if self.heal and tgt.fid == self.fid:
            if d <= self.rng and self.cd <= 0:
                tgt.hp = min(tgt.max_hp, tgt.hp + self.heal)
                tgt.healing = 1.1
                self.cd = self.atk_spd
                sim.events.append({'type': 'beam',
                                   'x1': self.x, 'y1': self.y,
                                   'x2': tgt.x,  'y2': tgt.y,
                                   'color': '#FFFFAA', 'lw': 2})
            elif d > self.rng:
                wx, wy = get_waypoint(self.x, self.y, tgt.x, tgt.y, sim.rivers, sim.bridges)
                self._move_to(wx, wy, dt, sp_mult, sim)
            return

        if self.is_bomber and d <= self.rng + 6:
            self._explode(sim)
            return

        if d <= eng_r:
            if self.cd <= 0:
                self._attack(tgt, sim)
        else:
            wx, wy = get_waypoint(self.x, self.y, tgt.x, tgt.y, sim.rivers, sim.bridges)
            self._move_to(wx, wy, dt, sp_mult, sim)
            if is_ranged and self.cd <= 0:
                near = self._nearest_enemy(self.rng, sim)
                if near:
                    self._attack(near, sim)

    # ── Target selection ─────────────────────────────────────────────────────

    def _target_score(self, e):
        sc = self._dist(e)
        if e.type == 'unit':
            sc -= 110
        elif e.type == 'castle':
            sc += 150
        return sc

    def _find_target(self, sim):
        # Confused units attack nearest friendly instead
        if self.confused:
            best, bd = None, float('inf')
            for e in sim.grid.query(self.x, self.y, 300):
                if e is self or e.dead or e.fid != self.fid:
                    continue
                d = self._dist(e)
                if d < bd:
                    bd, best = d, e
            return best

        # Healers seek wounded allies first
        if self.heal:
            hurt = next(
                (e for e in sim.grid.query(self.x, self.y, self.rng * 2)
                 if e.fid == self.fid and not e.dead and e.type == 'unit'
                 and e.hp < e.max_hp and e is not self), None)
            if hurt:
                return hurt

        # Prioritise threats near own castle
        home = sim.castle_cache.get(self.fid)
        if home:
            thr = next(
                (e for e in sim.grid.query(home.x, home.y, 220)
                 if not e.dead and e.fid != self.fid
                 and _dist(e.x, e.y, home.x, home.y) < 220), None)
            if thr:
                self._locked_target = thr
                return thr

        # General search with hysteresis to prevent target oscillation
        best, bd = None, float('inf')
        for e in sim.grid.query(self.x, self.y, 500):
            if e.fid == self.fid or e.dead:
                continue
            if getattr(e, 'stealthed', False) and not getattr(e, 'forest_cover', False) \
                    and self._dist(e) > 44:
                continue
            sc = self._target_score(e)
            if sc < bd:
                bd, best = sc, e

        if best is None and self._locked_target is not None:
            lt = self._locked_target
            if not lt.dead and lt.fid != self.fid:
                return lt

        locked = self._locked_target
        if locked is not None and not locked.dead and locked.fid != self.fid:
            if best is None or self._target_score(best) < self._target_score(locked) * 0.80:
                self._locked_target = best
        else:
            self._locked_target = best

        return self._locked_target

    def _nearest_enemy(self, r, sim):
        best, bd = None, r
        for e in sim.grid.query(self.x, self.y, r):
            if e.fid == self.fid or e.dead:
                continue
            if getattr(e, 'stealthed', False) and not getattr(e, 'forest_cover', False) \
                    and self._dist(e) > 44:
                continue
            d = self._dist(e)
            if d < bd:
                bd, best = d, e
        return best

    # ── Attack and damage ─────────────────────────────────────────────────────

    def _attack(self, target, sim):
        dmg = self.dmg * random.uniform(1 - 0.175, 1 + 0.175)

        # Blood Knight: 1× at full HP → 4× at zero HP
        if self.is_blood_knight:
            dmg *= 1.0 + 3.0 * (1.0 - max(0.0, self.hp / self.max_hp))

        # Stealth backstab bonus
        if self.utype in ('elf_rogue', 'phantom') and self.stealthed:
            dmg += self.burst_dmg
            self.stealthed     = False
            self.stealth_rev_t = 2.8
            sim.events.append({'type': 'sparks', 'x': target.x, 'y': target.y,
                                'color': sim.factions.get(self.fid, {}).get('color', '#fff'),
                                'n': 8})

        # Gnome Sapper: 5% self-destruct per shot
        if self.is_sapper and random.random() < 0.05:
            self._explode(sim)
            return

        if self.blood_rage:
            dmg *= 1.0 + (1.0 - self.hp / self.max_hp) * 1.2
        if self.charge_dmg and self.moved_dist > 60:
            dmg *= 1.6

        castle = sim.castle_cache.get(self.fid)
        if castle and castle.desperation_active:
            dmg *= 1.3

        # Fighting Pit damage bonus (Goblin Gang)
        if self.fid == 'goblin':
            pit_n = sim.faction_fighting_pit_count.get('goblin', 0)
            if pit_n:
                dmg *= 1.0 + 0.05 * pit_n

        self._deal_dmg(target, dmg, sim)

        # Craftsman 8% clockwork betrayal
        if self.is_craftsman and self.craftsman_minions and random.random() < 0.08:
            betrayer = random.choice(self.craftsman_minions)
            if not betrayer.dead:
                betrayer.fid = target.fid if target.fid != self.fid else 'neutral'
                betrayer._locked_target = self
                sim.events.append({'type': 'sparks', 'x': betrayer.x, 'y': betrayer.y,
                                   'color': '#FF4400', 'n': 6})

        fcolor = sim.factions.get(self.fid, {}).get('color', '#888')
        if self.aoe and not self.is_bomber:
            _aoe_hit(sim, target.x, target.y, self.aoe, dmg * 0.4, self.fid, fcolor, exclude=target)
        if self.chains:
            hits, prev = [target], target
            for _ in range(self.chains):
                prev = _chain_hit(sim, hits, prev, dmg, self.fid)
                if prev is None:
                    break

        if self.rng > 35:
            sim.events.append({'type': 'beam',
                               'x1': self.x,   'y1': self.y,
                               'x2': target.x, 'y2': target.y,
                               'color': fcolor, 'lw': 2})
        else:
            sim.events.append({'type': 'sparks', 'x': target.x, 'y': target.y,
                               'color': fcolor, 'n': 3})
        self.cd = self.atk_spd

    def _deal_dmg(self, e, dmg, sim):
        if e.type == 'castle':
            e.take_damage(dmg, self.fid)
            return
        if e.type == 'tower':
            e.take_damage(dmg * 0.8, self.fid)
            return
        if e.type == 'building':
            e.take_damage(dmg * 0.65, self.fid)
            return

        # Shield absorbs first
        if self.shield_hp > 0:
            absorbed     = min(e.shield_hp, dmg)
            e.shield_hp -= absorbed
            dmg         -= absorbed
            if dmg <= 0:
                return

        # Armor reduction (base + blacksmithy buff for yellow)
        armor = getattr(e, 'armor', 0.0)
        if e.fid == 'yellow':
            smith_n = sim.faction_blacksmithy_count.get('yellow', 0)
            armor   = max(armor, min(0.50, smith_n * 0.08))
        if armor > 0:
            dmg *= 1.0 - armor

        e.hp = max(0.0, e.hp - dmg)
        e.flash = 0.18
        if hasattr(e, 'combat_t'):
            e.combat_t = 0.0
        if getattr(e, 'stealthed', False) and not getattr(e, 'forest_cover', False):
            e.stealthed    = False
            e.stealth_rev_t = 2.5

        # On-hit effects
        if self.poison_on_hit:
            _apply_dot(e, 3, 4.0, f'poison_{self.id}')
        if self.fire_dot:
            _apply_dot(e, 6, 4.0, f'fire_{self.id}')
        if self.plague_dot:
            _apply_dot(e, 5, 20.0, 'plague_spread')
        if self.goblin_debuff:
            e.dmg = max(1.0, e.dmg * 0.90)
        if self.frost_slow_atk:
            e.frost_slow = 0.4
            e.frost_t    = 2.5
        if self.confuses and random.random() < 0.5:
            e.confused  = True
            e.confuse_t = 3.0
        if self.heal_on_kill and e.hp <= 0:
            self.hp = min(self.max_hp, self.hp + 12)
        if self.raise_dead and e.hp <= 0 and e.type == 'unit' and e.utype not in _UNDEAD_TYPES:
            ztype = 'zombie' if self.fid == 'bone' else 'crypt_skeleton'
            sim.entities.append(Unit(
                e.x + random.uniform(-6, 6),
                e.y + random.uniform(-6, 6),
                self.fid, ztype, sim))

    def _explode(self, sim):
        r      = self.aoe or 38.0
        fcolor = sim.factions.get(self.fid, {}).get('color', '#FF6600')
        _aoe_hit(sim, self.x, self.y, r, self.dmg, self.fid, fcolor)
        self.hp   = 0
        self.dead = True

    def _summon(self, sim, stype):
        sk = Unit(self.x + random.uniform(-9, 9),
                  self.y + random.uniform(-9, 9),
                  self.fid, stype, sim)
        sk.summoner_ref = self
        sim.entities.append(sk)
        self.my_minions.append(sk)

    def _do_build(self, dt, mult, sim):
        btype = self.assigned_btype
        if not btype:
            self.dead = True
            return
        if not self.build_target:
            f_data = sim.factions.get(self.fid, {})
            cx, cy = f_data.get('cx', self.x), f_data.get('cy', self.y)
            for _ in range(90):
                bx = cx + random.uniform(-180, 180)
                by = cy + random.uniform(-180, 180)
                if _dist(bx, by, cx, cy) < 90:
                    continue
                if bx < 24 or bx > MAP_W - 24 or by < 24 or by > MAP_H - 24:
                    continue
                if in_river(bx, by, sim.rivers, sim.bridges):
                    continue
                if any(e.type in ('building', 'castle') and _dist(bx, by, e.x, e.y) < 70
                       for e in sim.entities):
                    continue
                self.build_target = (bx, by)
                break
            if not self.build_target:
                self.build_target = (cx + random.uniform(-80, 80),
                                     cy + random.uniform(-80, 80))
        tx, ty = self.build_target
        if _dist(self.x, self.y, tx, ty) > 7:
            wx, wy = get_waypoint(self.x, self.y, tx, ty, sim.rivers, sim.bridges)
            self._move_to(wx, wy, dt, mult, sim)
        else:
            self.build_progress += dt
            if self.build_progress >= self.build_time:
                nb = Building(self.x, self.y, self.fid, btype)
                nb._sim_ref = sim
                sim.entities.append(nb)
                sim.events.append({'type': 'sparks', 'x': self.x, 'y': self.y,
                                   'color': sim.factions.get(self.fid, {}).get('hi', '#fff'),
                                   'n': 8})
                self.dead = True

    def _move_to(self, tx, ty, dt, mult, sim):
        ts  = terrain_speed(self.x, self.y, sim.rivers, sim.bridges, self.river_bonus)
        ang = math.atan2(ty - self.y, tx - self.x)
        spd = self.spd * mult * ts * dt
        self.x = _clamp(self.x + math.cos(ang) * spd, 8, MAP_W - 8)
        self.y = _clamp(self.y + math.sin(ang) * spd, 8, MAP_H - 8)
        if abs(tx - self.x) > 0.4:
            self.facing = 1 if tx > self.x else -1

    def to_dict(self):
        return {
            'id': self.id, 'type': 'unit', 'fid': self.fid, 'utype': self.utype,
            'x': self.x, 'y': self.y, 'hp': self.hp, 'max_hp': self.max_hp,
            'facing': self.facing, 'flash': self.flash,
            'stealthed': self.stealthed, 'forest_cover': self.forest_cover,
            'swarm_rushing': self.swarm_rushing,
            'confused': self.confused, 'dots': bool(self.dots),
            'frost_t': self.frost_t, 'healing': self.healing,
            'shield_hp': self.shield_hp,
            'build_progress': self.build_progress
                if (self.is_builder or self.is_bastion_builder) else 0,
            'is_builder': self.is_builder or self.is_bastion_builder,
        }


# ─── Titan ────────────────────────────────────────────────────────────────────

class Titan:
    def __init__(self, ttype, x, y, fid):
        self.id    = _new_id()
        self.ttype = ttype
        self.x, self.y = x, y
        self.fid   = fid
        self.type  = 'titan'
        s = UTYPES.get(ttype, UTYPES['elem_fire'])
        self.hp      = self.max_hp = float(s.get('hp', 900))
        self.dmg     = float(s.get('dmg', 50))
        self.spd     = float(s.get('spd', 30))
        self.rng     = float(s.get('rng', 90))
        self.atk_spd = float(s.get('atk_spd', 1.4))
        self.aoe     = float(s.get('aoe', 0))
        self.chains  = s.get('chains', 0)
        self.river_bonus = s.get('river_bonus', True)
        self.raise_dead  = s.get('raise_dead', False)
        self.dead  = False
        self.flash = 0.0
        self.facing = 1
        self.cd    = 2.0 + random.random() * 2
        self.life  = 270.0
        self.dots  = []   # titans can receive DoTs (wildfire, plague cloud, etc.)

    def _dist(self, o):
        return _dist(self.x, self.y, o.x, o.y)

    def take_damage(self, d, _fid):
        self.hp = max(0.0, self.hp - d)
        self.flash = 0.14
        if self.hp <= 0:
            self.dead = True

    def _hit(self, e, dmg, sim):
        if e.type == 'castle':
            e.take_damage(dmg * 0.35, None)
        elif e.type == 'tower':
            e.take_damage(dmg * 0.6, None)
        elif e.type == 'building':
            e.take_damage(dmg * 0.5, None)
        else:
            e.hp = max(0.0, e.hp - dmg)
            e.flash = 0.18
            if self.raise_dead and e.hp <= 0 and e.type == 'unit':
                sim.entities.append(Unit(e.x, e.y, self.fid, 'zombie', sim))

    def update(self, dt, sim):
        if self.dead:
            return
        self.cd   -= dt
        self.flash = max(0.0, self.flash - dt)
        self.life -= dt

        # Process any DoTs (wildfire, plague cloud, etc.)
        for dot in self.dots:
            self.hp  -= dot['dmg'] * dt
            dot['t'] -= dt
        self.dots = [d for d in self.dots if d['t'] > 0]
        if self.hp <= 0:
            self.dead = True
            sim.events.append({'type': 'boom', 'x': self.x, 'y': self.y,
                               'r': 80, 'color': '#8888AA'})
            return
        if self.life <= 0:
            self.dead = True
            sim.events.append({'type': 'boom', 'x': self.x, 'y': self.y,
                               'r': 80, 'color': '#8888AA'})
            return

        target = min(
            (e for e in sim.entities
             if e.type == 'castle' and e.fid != self.fid and not e.dead),
            key=lambda e: e.hp, default=None)
        if not target:
            return

        if self._dist(target) > 70:
            wx, wy = get_waypoint(self.x, self.y, target.x, target.y, sim.rivers, sim.bridges)
            ts  = terrain_speed(self.x, self.y, sim.rivers, sim.bridges, self.river_bonus)
            ang = math.atan2(wy - self.y, wx - self.x)
            self.x = _clamp(self.x + math.cos(ang) * self.spd * ts * dt, 8, MAP_W - 8)
            self.y = _clamp(self.y + math.sin(ang) * self.spd * ts * dt, 8, MAP_H - 8)
            self.facing = 1 if wx > self.x else -1

        if self.cd > 0:
            return
        self.cd    = self.atk_spd
        fcolor     = sim.factions.get(self.fid, {}).get('color', '#FF8800')
        self._do_attack(sim, fcolor)

    def _do_attack(self, sim, fcolor):
        tt = self.ttype

        if tt in ('elem_fire', 'chaos_titan', 'death_titan'):
            color = {'elem_fire': '#FF5511', 'chaos_titan': '#CC44FF',
                     'death_titan': '#C8C080'}.get(tt, fcolor)
            _aoe_hit(sim, self.x, self.y, self.aoe, self.dmg, self.fid, color)
            if tt == 'chaos_titan':
                for e in sim.grid.query(self.x, self.y, self.aoe):
                    if not e.dead and e.fid != self.fid and e.type == 'unit':
                        if _dist(e.x, e.y, self.x, self.y) < self.aoe:
                            e.confused  = True
                            e.confuse_t = 2.5
            if self.chains:
                hits, px, py = [], self.x, self.y
                for _ in range(self.chains):
                    nxt, nd = None, 160.0
                    for e in sim.grid.query(px, py, 160):
                        if e.dead or e.fid == self.fid or e in hits:
                            continue
                        d = _dist(e.x, e.y, px, py)
                        if d < nd:
                            nd, nxt = d, e
                    if nxt:
                        self._hit(nxt, self.dmg * 0.6, sim)
                        sim.events.append({'type': 'beam',
                                           'x1': px, 'y1': py,
                                           'x2': nxt.x, 'y2': nxt.y,
                                           'color': '#AADDFF', 'lw': 3})
                        hits.append(nxt)
                        px, py = nxt.x, nxt.y

        elif tt == 'elem_water':
            _aoe_hit(sim, self.x, self.y, self.aoe, self.dmg, self.fid, '#2299FF')
            hits, px, py = [], self.x, self.y
            for _ in range(self.chains):
                nxt, nd = None, 160.0
                for e in sim.grid.query(px, py, 160):
                    if e.dead or e.fid == self.fid or e in hits:
                        continue
                    d = _dist(e.x, e.y, px, py)
                    if d < nd:
                        nd, nxt = d, e
                if nxt:
                    self._hit(nxt, self.dmg * 0.6, sim)
                    sim.events.append({'type': 'beam',
                                       'x1': px, 'y1': py,
                                       'x2': nxt.x, 'y2': nxt.y,
                                       'color': '#88DDFF', 'lw': 4})
                    hits.append(nxt)
                    px, py = nxt.x, nxt.y

        elif tt == 'elem_earth':
            tgt = min(
                (e for e in sim.grid.query(self.x, self.y, 400)
                 if not e.dead and e.fid != self.fid),
                key=lambda e: self._dist(e), default=None)
            if tgt is None:
                tgt = min(
                    (e for e in sim.entities if not e.dead and e.fid != self.fid),
                    key=lambda e: self._dist(e), default=None)
            if tgt:
                col = '#C8C080' if tt == 'death_titan' else '#886633'
                _aoe_hit(sim, tgt.x, tgt.y, self.aoe, self.dmg * 0.8, self.fid, col)
                sim.events.append({'type': 'beam',
                                   'x1': self.x, 'y1': self.y,
                                   'x2': tgt.x,  'y2': tgt.y,
                                   'color': col, 'lw': 6})

        elif tt == 'elem_air':
            tgt = min(
                (e for e in sim.grid.query(self.x, self.y, 400)
                 if not e.dead and e.fid != self.fid),
                key=lambda e: self._dist(e), default=None)
            if tgt is None:
                tgt = min(
                    (e for e in sim.entities if not e.dead and e.fid != self.fid),
                    key=lambda e: self._dist(e), default=None)
            if tgt:
                self._hit(tgt, self.dmg * 2.2, sim)
                sim.events.append({'type': 'beam',
                                   'x1': self.x, 'y1': self.y,
                                   'x2': tgt.x,  'y2': tgt.y,
                                   'color': '#FFFFFF', 'lw': 7})

    def to_dict(self):
        return {'id': self.id, 'type': 'titan', 'ttype': self.ttype, 'fid': self.fid,
                'x': self.x, 'y': self.y, 'hp': self.hp, 'max_hp': self.max_hp,
                'flash': self.flash, 'life': self.life, 'facing': self.facing}