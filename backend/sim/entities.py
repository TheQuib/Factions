import math
import random
from .factions import (
    MAP_W, MAP_H, UTYPES, SPAWN_POOLS, FBLDG, FTITAN,
    PASSIVE_GOLD, BUILD_GOLD, SWARM_THRESHOLD,
    MAX_INC_BLDG, MAX_DEF_BLDG, MAX_SPECIAL, MAX_UNITS_PER_FACTION,
    TOWER_EXPIRE, TITAN_TIME,
)
from .terrain import terrain_speed, get_waypoint, in_river

_next_id = 0


def _new_id():
    global _next_id
    _next_id += 1
    return _next_id


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _dist(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


# ─── Arrow Tower ──────────────────────────────────────────────────────────────

class ArrowTower:
    def __init__(self, x, y):
        self.id = _new_id()
        self.x, self.y = x, y
        self.type = 'tower'
        self.fid = 'neutral'
        self.hp = self.max_hp = 200
        self.dead = False
        self.flash = 0.0
        self.cd = 1.0 + random.random()
        self.rng = 140
        self.dmg = 14
        self.atk_spd = 2.0
        self.last_hit_by = None
        self.inc_t = 0.0

    def update(self, dt, sim):
        if sim.game_time >= TOWER_EXPIRE:
            self.dead = True
            sim.events.append({'type': 'death', 'x': self.x, 'y': self.y, 'color': '#888888'})
            return
        self.flash = max(0.0, self.flash - dt)
        self.cd -= dt
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
        for e in sim.entities:
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
                self.hp = self.max_hp * 0.5
            else:
                self.dead = True

    def to_dict(self):
        return {'id': self.id, 'type': 'tower', 'fid': self.fid,
                'x': self.x, 'y': self.y, 'hp': self.hp, 'max_hp': self.max_hp, 'flash': self.flash}


# ─── Building ─────────────────────────────────────────────────────────────────

_INCOME_BTYPES = {
    'spore_cluster', 'granary', 'harbor', 'shrine', 'mycelium',
    'thieves_den', 'stable', 'ossuary', 'frost_shrine',
    'forge', 'blood_altar', 'foundry', 'dream_spire',
    'farm', 'library', 'stonecircle',
}

_BLDG_STATS = {
    'farm':          {'hp': 250, 'income': True},
    'library':       {'hp': 200, 'income': True},
    'stonecircle':   {'hp': 200, 'income': True},
    'tumor':         {'hp': 100},
    'brood_nest':    {'hp': 280, 'spawn_cd': 6, 'spawn_t': 4},
    'arcane_turret': {'hp': 220, 'rng': 160, 'dmg': 18, 'atk_spd': 1.8, 'cd': 2.0},
    'elf_forest':    {'hp': 320, 'zone_r': 75},
    'church':        {'hp': 300, 'heal_r': 80, 'heal_rate': 4, 'heal_cd': 0.5},
    'rampart':       {'hp': 450},
    'shadow_trap':   {'hp': 180, 'rng': 100, 'dmg': 22, 'atk_spd': 2.5, 'cd': 1.0},
    'storm_totem':   {'hp': 200, 'rng': 140, 'dmg': 14, 'atk_spd': 1.6, 'cd': 1.0, 'chains': 2},
    'death_shrine':  {'hp': 200, 'rng': 120, 'dmg': 16, 'atk_spd': 2.0, 'cd': 1.0, 'raise_dead': True},
    'ice_wall':      {'hp': 380, 'rng': 120, 'dmg': 10, 'atk_spd': 2.0, 'cd': 1.0, 'frost_slow': True},
    'spore_tower':   {'hp': 200, 'rng': 120, 'dmg': 8,  'atk_spd': 1.5, 'cd': 1.0, 'aoe': 40},
    'fire_pit':      {'hp': 220, 'rng': 90,  'dmg': 15, 'atk_spd': 1.5, 'cd': 1.0, 'burn_aura': True},
    'beacon':        {'hp': 200, 'heal_r': 90, 'heal_rate': 5, 'heal_cd': 0.4},
    'tide_shrine':   {'hp': 200, 'rng': 130, 'dmg': 14, 'atk_spd': 1.8, 'cd': 1.0, 'aoe': 45},
    'rage_totem':    {'hp': 180},
    'veil_shrine':   {'hp': 180, 'rng': 130, 'dmg': 10, 'atk_spd': 2.0, 'cd': 1.0, 'confuses': True},
}


class Building:
    def __init__(self, x, y, fid, btype):
        self.id = _new_id()
        self.x, self.y = x, y
        self.fid = fid
        self.btype = btype
        self.type = 'building'
        self.dead = False
        self.flash = 0.0
        stats = _BLDG_STATS.get(btype, {'hp': 200})
        self.hp = self.max_hp = stats.get('hp', 200)
        self.income = btype in _INCOME_BTYPES
        self.inc_t = 0.0
        self.heal_t = 0.0
        self.zone_t = 0.0
        self.rng  = stats.get('rng', 0)
        self.dmg  = stats.get('dmg', 0)
        self.atk_spd = stats.get('atk_spd', 0)
        self.cd   = stats.get('cd', 0.0)
        self.chains = stats.get('chains', 0)
        self.aoe  = stats.get('aoe', 0)
        self.frost_slow  = stats.get('frost_slow', False)
        self.raise_dead  = stats.get('raise_dead', False)
        self.confuses    = stats.get('confuses', False)
        self.burn_aura   = stats.get('burn_aura', False)
        self.heal_r    = stats.get('heal_r', 0)
        self.heal_rate = stats.get('heal_rate', 0)
        self.heal_cd   = stats.get('heal_cd', 0)
        self.zone_r    = stats.get('zone_r', 0)
        self.spawn_cd  = stats.get('spawn_cd', 0)
        self.spawn_t   = stats.get('spawn_t', 0)
        self.minions   = []

    def update(self, dt, sim):
        self.flash = max(0.0, self.flash - dt)
        if self.income:
            self.inc_t += dt
            if self.inc_t >= 1.0:
                self.inc_t = 0.0
                c = sim.castle_cache.get(self.fid)
                if c:
                    c.gold += BUILD_GOLD

        if self.btype == 'brood_nest':
            self.minions = [m for m in self.minions if not m.dead and m.hp > 0]
            if len(self.minions) < 5:
                self.spawn_t -= dt
                if self.spawn_t <= 0:
                    self.spawn_t = self.spawn_cd
                    self._spawn_bug(sim)

        if self.rng and self.dmg:
            self.cd -= dt
            if self.cd <= 0:
                self._shoot(sim)

        if self.btype in ('church', 'beacon') and self.heal_r:
            self.heal_t -= dt
            if self.heal_t <= 0:
                self.heal_t = self.heal_cd
                for e in sim.entities:
                    if e.fid != self.fid or e.dead:
                        continue
                    if _dist(e.x, e.y, self.x, self.y) <= self.heal_r:
                        if hasattr(e, 'hp') and hasattr(e, 'max_hp') and e.hp < e.max_hp:
                            e.hp = min(e.max_hp, e.hp + self.heal_rate * self.heal_cd)
                            if hasattr(e, 'healing'):
                                e.healing = 0.6

        if self.btype == 'elf_forest' and self.zone_r:
            self.zone_t += dt
            if self.zone_t >= 0.5:
                self.zone_t = 0.0
                for e in sim.entities:
                    if e.dead:
                        continue
                    d = _dist(e.x, e.y, self.x, self.y)
                    if e.fid == self.fid and d <= self.zone_r:
                        if hasattr(e, 'utype') and e.utype == 'elf_rogue' and not e.stealthed:
                            e.stealthed = True
                        if hasattr(e, 'forest_cover'):
                            e.forest_cover = True
                    elif e.fid == self.fid and hasattr(e, 'forest_cover'):
                        e.forest_cover = False
                    if e.fid != self.fid and d <= self.zone_r and hasattr(e, 'forest_slow'):
                        e.forest_slow = 0.55
                    elif e.fid != self.fid and hasattr(e, 'forest_slow') and d > self.zone_r:
                        e.forest_slow = 1.0

    def _spawn_bug(self, sim):
        ang = random.random() * math.pi * 2
        bug = Unit(self.x + math.cos(ang) * 18, self.y + math.sin(ang) * 18, self.fid, 'brood_bug', sim)
        bug.home_building = self
        sim.entities.append(bug)
        self.minions.append(bug)

    def _shoot(self, sim):
        tgt, bd = None, self.rng
        for e in sim.entities:
            if e.fid == self.fid or e.dead:
                continue
            d = _dist(e.x, e.y, self.x, self.y)
            if d < bd:
                bd, tgt = d, e
        if not tgt:
            self.cd = 0.8
            return
        dmg = self.dmg + (random.random() - 0.5) * 6
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
            if self.frost_slow:
                tgt.frost_slow = 0.4
                tgt.frost_t = 2.5
            if getattr(self, 'poison_on_hit', False):
                tgt.dots.append({'dmg': 3, 't': 4.0})
            if self.confuses and random.random() < 0.5:
                tgt.confused = True
                tgt.confuse_t = 3.0
            if self.raise_dead and tgt.hp <= 0:
                sk = Unit(tgt.x, tgt.y, self.fid, 'skeleton', sim)
                sim.entities.append(sk)
        sim.events.append({'type': 'beam', 'x1': self.x, 'y1': self.y,
                           'x2': tgt.x, 'y2': tgt.y, 'color': fcolor, 'lw': 2})
        if self.aoe:
            sim.events.append({'type': 'boom', 'x': tgt.x, 'y': tgt.y, 'r': self.aoe, 'color': fcolor})
            for e in sim.entities:
                if e.fid == self.fid or e.dead or e is tgt:
                    continue
                if _dist(e.x, e.y, tgt.x, tgt.y) < self.aoe:
                    e.hp = max(0.0, e.hp - dmg * 0.4)
                    e.flash = 0.12
        if self.chains:
            hits, prev = [tgt], tgt
            for _ in range(self.chains):
                nxt, nd = None, 120.0
                for e in sim.entities:
                    if e.fid == self.fid or e.dead or e in hits:
                        continue
                    d = _dist(e.x, e.y, prev.x, prev.y)
                    if d < nd:
                        nd, nxt = d, e
                if nxt:
                    nxt.hp = max(0.0, nxt.hp - dmg * 0.55)
                    nxt.flash = 0.12
                    sim.events.append({'type': 'beam', 'x1': prev.x, 'y1': prev.y,
                                       'x2': nxt.x, 'y2': nxt.y, 'color': '#AADDFF', 'lw': 2})
                    hits.append(nxt)
                    prev = nxt
        self.cd = self.atk_spd

    def take_damage(self, d, _fid):
        self.hp = max(0.0, self.hp - d)
        self.flash = 0.18
        if self.hp <= 0:
            self.dead = True

    def to_dict(self):
        return {'id': self.id, 'type': 'building', 'fid': self.fid, 'btype': self.btype,
                'x': self.x, 'y': self.y, 'hp': self.hp, 'max_hp': self.max_hp, 'flash': self.flash}


# ─── Castle ───────────────────────────────────────────────────────────────────

class Castle:
    def __init__(self, x, y, fid):
        self.id = _new_id()
        self.x, self.y = x, y
        self.fid = fid
        self.type = 'castle'
        self.hp = self.max_hp = 1600.0
        self.gold = 120.0
        self.dead = False
        self.flash = 0.0
        self.spawn_t = 1.0 + random.random() * 2
        self.build_cd = 0.0
        self.swarm_state = 'gathering'
        self.swarm_target = None
        self.swarm_check_t = 0.0
        self.desperation_active = False
        self.desperation_cooldown = 0.0

    def update(self, dt, sim):
        self.gold += PASSIVE_GOLD * dt
        self.spawn_t -= dt
        self.build_cd = max(0.0, self.build_cd - dt)

        if self.desperation_cooldown > 0:
            self.desperation_cooldown -= dt
        elif not self.desperation_active and self.hp / self.max_hp < 0.28:
            self.desperation_active = True

        if self.desperation_active:
            self.hp = min(self.max_hp * 0.40, self.hp + 7 * dt)
            if self.hp / self.max_hp >= 0.40:
                self.desperation_active = False
                self.desperation_cooldown = 120.0
                sim.events.append({'type': 'sparks', 'x': self.x, 'y': self.y,
                                   'color': sim.factions.get(self.fid, {}).get('hi', '#FFFFFF'), 'n': 10})

        if self.spawn_t <= 0:
            self._try_spawn(sim)
            self.spawn_t = (0.65 if self.fid == 'red' else 1.8) + random.random() * 0.9

        if self.fid == 'red':
            self.swarm_check_t -= dt
            if self.swarm_check_t <= 0:
                self.swarm_check_t = 2.0
                self._update_swarm(sim)

    def _update_swarm(self, sim):
        swarms = [e for e in sim.entities
                  if e.fid == 'red' and e.type == 'unit' and e.utype == 'hive_swarm' and not e.dead]
        if self.swarm_state == 'gathering':
            if len(swarms) >= SWARM_THRESHOLD:
                weak = min(
                    (e for e in sim.entities if e.type == 'castle' and e.fid != 'red' and not e.dead),
                    key=lambda e: e.hp, default=None)
                if weak:
                    self.swarm_state = 'rushing'
                    self.swarm_target = weak.fid
                    for s in swarms:
                        s.swarm_rushing = True
                        s.swarm_target_fid = weak.fid
        else:
            target_alive = self.swarm_target in sim.castle_cache
            still_rushing = sum(1 for s in swarms if s.swarm_rushing)
            if not target_alive or still_rushing < 3:
                self.swarm_state = 'gathering'
                self.swarm_target = None
                for s in swarms:
                    s.swarm_rushing = False
                    s.swarm_target_fid = None

    def _try_spawn(self, sim):
        f = self.fid
        bldg_cfg = FBLDG.get(f)
        if not bldg_cfg:
            return
        if (sim.faction_unit_count.get(f, 0)) >= MAX_UNITS_PER_FACTION:
            return
        inc_count = sum(1 for e in sim.entities if e.type == 'building' and e.fid == f and e.income)
        def_count = sum(1 for e in sim.entities
                        if e.type == 'building' and e.fid == f and not e.income
                        and e.btype != bldg_cfg.get('special'))
        sp_count = (sum(1 for e in sim.entities
                        if e.type == 'building' and e.fid == f and e.btype == bldg_cfg.get('special'))
                    if bldg_cfg.get('special') else 0)
        has_builder = any(e.fid == f and e.type == 'unit' and UTYPES.get(e.utype, {}).get('is_builder')
                          for e in sim.entities)
        builder_type = bldg_cfg.get('builder', f + '_builder')

        if not has_builder and inc_count < MAX_INC_BLDG and self.gold >= 30 and self.build_cd <= 0:
            return self._spawn_builder(builder_type, bldg_cfg['income'], sim)
        if not has_builder and def_count < MAX_DEF_BLDG and self.gold >= 30 and self.build_cd <= 0 and random.random() < 0.5:
            return self._spawn_builder(builder_type, bldg_cfg['defense'], sim)
        if (bldg_cfg.get('special') and not has_builder and sp_count < MAX_SPECIAL
                and self.gold >= 30 and self.build_cd <= 0 and random.random() < 0.3):
            return self._spawn_builder(builder_type, bldg_cfg['special'], sim)

        pool = SPAWN_POOLS.get(f, ['iron_foot'])
        utype = random.choice(pool)
        cost = UTYPES.get(utype, {}).get('cost', 40)
        if self.gold >= cost:
            self.gold -= cost
            sim.entities.append(Unit(
                self.x + random.uniform(-17, 17),
                self.y + random.uniform(-17, 17),
                f, utype, sim))

    def _spawn_builder(self, utype, btype, sim):
        if utype not in UTYPES:
            return
        cost = UTYPES[utype].get('cost', 30)
        if self.gold < cost:
            return
        self.gold -= cost
        self.build_cd = 40.0
        u = Unit(self.x + random.uniform(-12, 12), self.y + random.uniform(-12, 12), self.fid, utype, sim)
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
                'desperation_active': self.desperation_active,
                'desperation_cooldown': self.desperation_cooldown}


# ─── Unit ─────────────────────────────────────────────────────────────────────

class Unit:
    def __init__(self, x, y, fid, utype, sim):
        self.id = _new_id()
        self.x, self.y = x, y
        self.fid = fid
        self.utype = utype
        self.type = 'unit'
        s = UTYPES.get(utype, {'hp': 30, 'dmg': 8, 'spd': 40, 'rng': 22, 'atk_spd': 1.5, 'size': 5, 'cost': 30})
        self.hp = self.max_hp = float(s.get('hp', 30))
        self.dmg      = s.get('dmg', 8)
        self.spd      = s.get('spd', 40)
        self.rng      = s.get('rng', 22)
        self.atk_spd  = s.get('atk_spd', 1.5)
        self.size     = s.get('size', 5)
        self.aoe      = s.get('aoe', 0)
        self.chains   = s.get('chains', 0)
        self.heal     = s.get('heal', 0)
        self.burst_dmg    = s.get('burst_dmg', 0)
        self.is_bomber    = s.get('is_bomber', False)
        self.is_builder   = s.get('is_builder', False)
        self.build_time   = s.get('build_time', 10)
        self.assigned_btype = s.get('b_type', None)
        self.spawns       = s.get('spawns', None)
        self.summons      = s.get('summons', None)
        self.no_regen     = s.get('no_regen', False)
        self.river_bonus  = s.get('river_bonus', False)
        self.poison_on_hit = s.get('poison_on_hit', False)
        self.frost_slow_atk = s.get('frost_slow', False)
        self.confuses     = s.get('confuses', False)
        self.raise_dead   = s.get('raise_dead', False)
        self.heal_on_kill = s.get('heal_on_kill', False)
        self.blood_rage   = s.get('blood_rage', False)
        self.charge_dmg   = s.get('charge_dmg', False)
        self.burn_aura    = s.get('burn_aura', False)
        self.dead = False
        self.flash = 0.0
        self.facing = 1
        self.wob = random.random() * math.pi * 2
        self.cd = random.random() * self.atk_spd
        self.combat_t = 0.0
        self.healing = 0.0
        self.stealthed = utype in ('elf_rogue', 'phantom')
        self.stealth_rev_t = 0.0
        self.forest_cover = False
        self.forest_slow = 1.0
        self.build_target = None
        self.build_progress = 0.0
        self.my_minions = []
        self.necro_t = 0.0
        self.summoner_ref = None
        self.home_building = None
        self.swarm_rushing = False
        self.swarm_target_fid = None
        self.dots = []
        self.frost_t = 0.0
        self.frost_slow = 1.0
        self.confused = False
        self.confuse_t = 0.0
        self._locked_target = None  # persists between ticks to prevent oscillation
        self.prev_x, self.prev_y = x, y
        self.moved_dist = 0.0
        self._sim = sim  # weak back-reference for terrain helpers

    def _dist(self, o):
        return _dist(self.x, self.y, o.x, o.y)

    def update(self, dt, sim):
        if self.hp <= 0:
            self.dead = True
            return
        self.cd -= dt
        self.flash = max(0.0, self.flash - dt)
        self.healing = max(0.0, self.healing - dt)
        self.wob += dt * 1.7

        # DOTs
        for dot in self.dots:
            self.hp -= dot['dmg'] * dt
            dot['t'] -= dt
        self.dots = [d for d in self.dots if d['t'] > 0]
        if self.hp <= 0:
            self.dead = True
            return

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

        # Combat regen
        if self.fid == 'red' and not self.no_regen and self.hp < self.max_hp:
            self.combat_t += dt
            if self.combat_t > 2.4:
                self.hp = min(self.max_hp, self.hp + 11 * dt)
        if self.fid == 'steel' and not self.no_regen and self.hp < self.max_hp:
            self.combat_t += dt
            if self.combat_t > 3.0:
                self.hp = min(self.max_hp, self.hp + 5 * dt)

        if self.charge_dmg:
            md = _dist(self.x, self.y, self.prev_x, self.prev_y)
            self.moved_dist = self.moved_dist * 0.92 + md
        self.prev_x, self.prev_y = self.x, self.y

        # Mania — all units freeze in place
        if sim.mania_t > 0:
            return

        # Speed multiplier
        sp_mult = self.forest_slow
        if sim.blizzard_t > 0:
            sp_mult *= 0.28
        if self.frost_t > 0:
            sp_mult *= 0.6
        my_castle = sim.castle_cache.get(self.fid)
        if my_castle and my_castle.desperation_active:
            sp_mult *= 1.25
        if self.fid == 'red':
            for tmr in sim.tumor_list:
                if _dist(self.x, self.y, tmr.x, tmr.y) < 62:
                    sp_mult = max(sp_mult, 1.5)
                    break
        if self.fid == 'crim':
            for rt in sim.rage_totem_list:
                if _dist(self.x, self.y, rt.x, rt.y) < 80:
                    sp_mult *= 1.2
                    break

        # Necro minion management
        if self.summons:
            self.my_minions = [m for m in self.my_minions if not m.dead and m.hp > 0]
            if len(self.my_minions) < 3:
                self.necro_t += dt
                if self.necro_t >= 8.0:
                    self._summon(sim)
                    self.necro_t = 0.0

        # Skeleton bodyguard AI
        if self.utype == 'skeleton' and self.summoner_ref:
            sm = self.summoner_ref
            if sm.dead or sm.hp <= 0:
                self.hp = 0
                self.dead = True
                return
            threat, td = None, 180.0
            for e in sim.entities:
                if e.fid == self.fid or e.dead:
                    continue
                d = _dist(e.x, e.y, sm.x, sm.y)
                if d < td:
                    td, threat = d, e
            if threat:
                ang = math.atan2(threat.y - sm.y, threat.x - sm.x)
                self._move_to(sm.x + math.cos(ang) * 26, sm.y + math.sin(ang) * 26, dt, 1.0, sim)
                self.facing = 1 if threat.x > self.x else -1
                if self._dist(threat) <= self.rng and self.cd <= 0:
                    self.cd = self.atk_spd
                    self._deal_dmg(threat, self.dmg, sim)
            else:
                oa = self.wob * 0.4
                self._move_to(sm.x + math.cos(oa) * 24, sm.y + math.sin(oa) * 24, dt, 1.0, sim)
            return

        if self.spawns and self.cd <= 0:
            sim.entities.append(Unit(self.x, self.y, self.fid, self.spawns, sim))
            self.cd = self.atk_spd

        if self.is_builder:
            self._do_build(dt, sp_mult, sim)
            return
        if self.utype == 'brood_bug' and self.home_building and not self.home_building.dead:
            self._brood_bug_ai(dt, sp_mult, sim)
            return
        if self.utype == 'hive_swarm':
            self._swarm_ai(dt, sp_mult, sim)
            return
        self._combat_ai(dt, sp_mult, sim)

    def _swarm_ai(self, dt, sp_mult, sim):
        if self.swarm_rushing and self.swarm_target_fid:
            tc = sim.castle_cache.get(self.swarm_target_fid)
            if not tc:
                self.swarm_rushing = False
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
                self._move_to(home.x + math.cos(oa) * 55, home.y + math.sin(oa) * 55, dt, sp_mult * 0.6, sim)
                threat = self._nearest_enemy(90, sim)
                if threat and self.cd <= 0:
                    self._attack(threat, sim)

    def _brood_bug_ai(self, dt, sp_mult, sim):
        home = self.home_building
        threat = self._nearest_enemy(120, sim)
        if threat:
            if self._dist(threat) <= self.rng:
                if self.cd <= 0:
                    self._attack(threat, sim)
            else:
                self._move_to(threat.x, threat.y, dt, sp_mult, sim)
            self.facing = 1 if threat.x > self.x else -1
        else:
            if self._dist(home) > 40:
                ang = math.atan2(home.y - self.y, home.x - self.x)
                ts = terrain_speed(self.x, self.y, sim.rivers, sim.bridges, self.river_bonus)
                self.x += math.cos(ang) * self.spd * sp_mult * ts * dt
                self.y += math.sin(ang) * self.spd * sp_mult * ts * dt

    def _combat_ai(self, dt, sp_mult, sim):
        tgt = self._find_target(sim)
        if not tgt:
            return
        d = self._dist(tgt)
        is_ranged = self.rng > 40
        eng_r = self.rng * 0.62 if is_ranged else self.rng
        if self.heal and tgt.fid == self.fid:
            if d <= self.rng and self.cd <= 0:
                tgt.hp = min(tgt.max_hp, tgt.hp + self.heal)
                tgt.healing = 1.1
                self.cd = self.atk_spd
                sim.events.append({'type': 'beam', 'x1': self.x, 'y1': self.y,
                                   'x2': tgt.x, 'y2': tgt.y, 'color': '#FFFFAA', 'lw': 2})
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

    def _target_score(self, e):
        """Lower score = higher priority."""
        sc = self._dist(e)
        if e.type == 'unit':
            sc -= 110
        elif e.type == 'castle':
            sc += 150
        return sc

    def _find_target(self, sim):
        if self.confused:
            best, bd = None, float('inf')
            for e in sim.entities:
                if e is self or e.dead or e.fid != self.fid:
                    continue
                d = self._dist(e)
                if d < bd:
                    bd, best = d, e
            return best
        if self.heal:
            hurt = next((e for e in sim.entities
                         if e.fid == self.fid and not e.dead and e.type == 'unit'
                         and e.hp < getattr(e, 'max_hp', e.hp) and e is not self), None)
            if hurt:
                return hurt
        home = sim.castle_cache.get(self.fid)
        if home:
            thr = next((e for e in sim.entities
                        if not e.dead and e.fid != self.fid and _dist(e.x, e.y, home.x, home.y) < 220), None)
            if thr:
                self._locked_target = thr
                return thr

        # Find the best candidate
        best, bd = None, float('inf')
        for e in sim.entities:
            if e.fid == self.fid or e.dead:
                continue
            if getattr(e, 'stealthed', False) and not getattr(e, 'forest_cover', False) and self._dist(e) > 44:
                continue
            sc = self._target_score(e)
            if sc < bd:
                bd, best = sc, e

        # Hysteresis: only switch away from the locked target if the new candidate
        # is meaningfully better (20% lower score), preventing oscillation.
        locked = self._locked_target
        if locked is not None and not locked.dead and locked.fid != self.fid:
            if best is None or self._target_score(best) < self._target_score(locked) * 0.80:
                self._locked_target = best
            # else stick with locked target
        else:
            self._locked_target = best

        return self._locked_target

    def _nearest_enemy(self, r, sim):
        best, bd = None, r
        for e in sim.entities:
            if e.fid == self.fid or e.dead:
                continue
            if getattr(e, 'stealthed', False) and not getattr(e, 'forest_cover', False) and self._dist(e) > 44:
                continue
            d = self._dist(e)
            if d < bd:
                bd, best = d, e
        return best

    def _attack(self, target, sim):
        dmg = self.dmg + random.uniform(-self.dmg * 0.175, self.dmg * 0.175)
        if self.utype in ('elf_rogue', 'phantom') and self.stealthed:
            dmg += self.burst_dmg
            self.stealthed = False
            self.stealth_rev_t = 2.8
            sim.events.append({'type': 'sparks', 'x': target.x, 'y': target.y,
                                'color': sim.factions.get(self.fid, {}).get('color', '#fff'), 'n': 8})
        if self.blood_rage:
            dmg *= 1 + (1 - self.hp / self.max_hp) * 1.2
        if self.charge_dmg and self.moved_dist > 60:
            dmg *= 1.6
        my_castle = sim.castle_cache.get(self.fid)
        if my_castle and my_castle.desperation_active:
            dmg *= 1.3
        self._deal_dmg(target, dmg, sim)
        fcolor = sim.factions.get(self.fid, {}).get('color', '#888')
        if self.aoe and not self.is_bomber:
            sim.events.append({'type': 'boom', 'x': target.x, 'y': target.y, 'r': self.aoe, 'color': fcolor})
            for e in sim.entities:
                if e.fid == self.fid or e.dead or e is target:
                    continue
                if _dist(e.x, e.y, target.x, target.y) < self.aoe:
                    self._deal_dmg(e, dmg * 0.4, sim)
        if self.chains:
            hits, prev = [target], target
            for _ in range(self.chains):
                nxt, nd = None, 120.0
                for e in sim.entities:
                    if e.fid == self.fid or e.dead or e in hits:
                        continue
                    d = _dist(e.x, e.y, prev.x, prev.y)
                    if d < nd:
                        nd, nxt = d, e
                if nxt:
                    self._deal_dmg(nxt, dmg * 0.55, sim)
                    sim.events.append({'type': 'beam', 'x1': prev.x, 'y1': prev.y,
                                       'x2': nxt.x, 'y2': nxt.y, 'color': '#AADDFF', 'lw': 3})
                    hits.append(nxt)
                    prev = nxt
        if self.rng > 35:
            sim.events.append({'type': 'beam', 'x1': self.x, 'y1': self.y,
                               'x2': target.x, 'y2': target.y, 'color': fcolor, 'lw': 2})
        else:
            sim.events.append({'type': 'sparks', 'x': target.x, 'y': target.y, 'color': fcolor, 'n': 3})
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
        e.hp = max(0.0, e.hp - dmg)
        e.flash = 0.18
        if hasattr(e, 'combat_t'):
            e.combat_t = 0.0
        if getattr(e, 'stealthed', False) and not getattr(e, 'forest_cover', False):
            e.stealthed = False
            e.stealth_rev_t = 2.5
        if self.poison_on_hit:
            e.dots.append({'dmg': 3, 't': 4.0})
        if self.frost_slow_atk:
            e.frost_slow = 0.4
            e.frost_t = 2.5
        if self.confuses and random.random() < 0.5:
            e.confused = True
            e.confuse_t = 3.0
        if self.heal_on_kill and e.hp <= 0:
            self.hp = min(self.max_hp, self.hp + 12)
        if self.raise_dead and e.hp <= 0 and e.type == 'unit' and 'skeleton' not in e.utype:
            sk = Unit(e.x + random.uniform(-6, 6), e.y + random.uniform(-6, 6), self.fid, 'skeleton', sim)
            sim.entities.append(sk)

    def _explode(self, sim):
        r = self.aoe or 38
        fcolor = sim.factions.get(self.fid, {}).get('color', '#FF6600')
        sim.events.append({'type': 'boom', 'x': self.x, 'y': self.y, 'r': r, 'color': fcolor})
        for e in sim.entities:
            if e.fid == self.fid or e.dead:
                continue
            if _dist(e.x, e.y, self.x, self.y) < r:
                self._deal_dmg(e, self.dmg, sim)
        self.hp = 0
        self.dead = True

    def _summon(self, sim):
        sk = Unit(self.x + random.uniform(-9, 9), self.y + random.uniform(-9, 9), self.fid, 'skeleton', sim)
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
            bx = by = None
            for _ in range(90):
                bx = cx + random.uniform(-180, 180)
                by = cy + random.uniform(-180, 180)
                if _dist(bx, by, cx, cy) < 90:
                    continue
                if bx < 24 or bx > MAP_W - 24 or by < 24 or by > MAP_H - 24:
                    continue
                if in_river(bx, by, sim.rivers, sim.bridges):
                    continue
                if any((e.type in ('building', 'castle') and _dist(bx, by, e.x, e.y) < 70)
                       for e in sim.entities):
                    continue
                break
            self.build_target = (bx, by)
        tx, ty = self.build_target
        if _dist(self.x, self.y, tx, ty) > 7:
            wx, wy = get_waypoint(self.x, self.y, tx, ty, sim.rivers, sim.bridges)
            self._move_to(wx, wy, dt, mult, sim)
        else:
            self.build_progress += dt
            if self.build_progress >= self.build_time:
                sim.entities.append(Building(self.x, self.y, self.fid, btype))
                sim.events.append({'type': 'sparks', 'x': self.x, 'y': self.y,
                                   'color': sim.factions.get(self.fid, {}).get('hi', '#fff'), 'n': 8})
                self.dead = True

    def _move_to(self, tx, ty, dt, mult, sim):
        ts = terrain_speed(self.x, self.y, sim.rivers, sim.bridges, self.river_bonus)
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
            'confused': self.confused,
            'dots': bool(self.dots),
            'frost_t': self.frost_t,
            'healing': self.healing,
            'build_progress': self.build_progress if self.is_builder else 0,
            'is_builder': self.is_builder,
        }


# ─── Titan ────────────────────────────────────────────────────────────────────

class Titan:
    def __init__(self, ttype, x, y, fid):
        self.id = _new_id()
        self.ttype = ttype
        self.x, self.y = x, y
        self.fid = fid
        self.type = 'titan'
        s = UTYPES.get(ttype, UTYPES['elem_fire'])
        self.hp = self.max_hp = float(s.get('hp', 900))
        self.dmg     = s.get('dmg', 50)
        self.spd     = s.get('spd', 30)
        self.rng     = s.get('rng', 90)
        self.atk_spd = s.get('atk_spd', 1.4)
        self.aoe     = s.get('aoe', 0)
        self.chains  = s.get('chains', 0)
        self.river_bonus = s.get('river_bonus', True)
        self.dead = False
        self.flash = 0.0
        self.facing = 1
        self.cd = 2.0 + random.random() * 2
        self.life = 270.0

    def _dist(self, o):
        return _dist(self.x, self.y, o.x, o.y)

    def take_damage(self, d, _fid):
        self.hp = max(0.0, self.hp - d)
        self.flash = 0.14
        if self.hp <= 0:
            self.dead = True

    def update(self, dt, sim):
        if self.dead:
            return
        self.cd -= dt
        self.flash = max(0.0, self.flash - dt)
        self.life -= dt
        if self.life <= 0:
            self.dead = True
            sim.events.append({'type': 'boom', 'x': self.x, 'y': self.y, 'r': 80, 'color': '#8888AA'})
            return
        target = min(
            (e for e in sim.entities if e.type == 'castle' and e.fid != self.fid and not e.dead),
            key=lambda e: e.hp, default=None)
        if not target:
            return
        if self._dist(target) > 70:
            wx, wy = get_waypoint(self.x, self.y, target.x, target.y, sim.rivers, sim.bridges)
            ts = terrain_speed(self.x, self.y, sim.rivers, sim.bridges, self.river_bonus)
            ang = math.atan2(wy - self.y, wx - self.x)
            self.x = _clamp(self.x + math.cos(ang) * self.spd * ts * dt, 8, MAP_W - 8)
            self.y = _clamp(self.y + math.sin(ang) * self.spd * ts * dt, 8, MAP_H - 8)
            self.facing = 1 if wx > self.x else -1
        if self.cd > 0:
            return
        self.cd = self.atk_spd
        fcolor = sim.factions.get(self.fid, {}).get('color', '#FF8800')
        self._do_attack(sim, fcolor)

    def _hit(self, e, dmg, sim):
        if e.type == 'castle':
            e.take_damage(dmg * 0.35, None)
        elif e.type == 'tower':
            e.take_damage(dmg * 0.6, None)
        elif e.type == 'building':
            e.take_damage(dmg * 0.5, None)
        elif hasattr(e, 'hp'):
            e.hp = max(0.0, e.hp - dmg)
            e.flash = 0.18

    def _do_attack(self, sim, fcolor):
        if self.ttype == 'elem_fire':
            sim.events.append({'type': 'boom', 'x': self.x, 'y': self.y, 'r': self.aoe, 'color': '#FF5511'})
            for e in sim.entities:
                if not e.dead and e.fid != self.fid and _dist(e.x, e.y, self.x, self.y) < self.aoe:
                    self._hit(e, self.dmg, sim)
        elif self.ttype == 'elem_water':
            sim.events.append({'type': 'boom', 'x': self.x, 'y': self.y, 'r': self.aoe, 'color': '#2299FF'})
            for e in sim.entities:
                if not e.dead and e.fid != self.fid and _dist(e.x, e.y, self.x, self.y) < self.aoe:
                    self._hit(e, self.dmg, sim)
            hits, prev = [], {'x': self.x, 'y': self.y}
            for _ in range(self.chains):
                nxt, nd = None, 160.0
                for e in sim.entities:
                    if e.dead or e.fid == self.fid or e in hits:
                        continue
                    d = _dist(e.x, e.y, prev['x'], prev['y'])
                    if d < nd:
                        nd, nxt = d, e
                if nxt:
                    self._hit(nxt, self.dmg * 0.6, sim)
                    sim.events.append({'type': 'beam', 'x1': prev['x'], 'y1': prev['y'],
                                       'x2': nxt.x, 'y2': nxt.y, 'color': '#88DDFF', 'lw': 4})
                    hits.append(nxt)
                    prev = {'x': nxt.x, 'y': nxt.y}
        elif self.ttype == 'elem_earth':
            tgt = min((e for e in sim.entities if not e.dead and e.fid != self.fid),
                      key=lambda e: self._dist(e), default=None)
            if tgt:
                sim.events.append({'type': 'boom', 'x': tgt.x, 'y': tgt.y, 'r': self.aoe, 'color': '#886633'})
                sim.events.append({'type': 'beam', 'x1': self.x, 'y1': self.y,
                                   'x2': tgt.x, 'y2': tgt.y, 'color': '#AA8844', 'lw': 6})
                for e in sim.entities:
                    if not e.dead and e.fid != self.fid and _dist(e.x, e.y, tgt.x, tgt.y) < self.aoe:
                        self._hit(e, self.dmg * 0.8, sim)
        elif self.ttype == 'elem_air':
            tgt = min((e for e in sim.entities if not e.dead and e.fid != self.fid),
                      key=lambda e: self._dist(e), default=None)
            if tgt:
                self._hit(tgt, self.dmg * 2.2, sim)
                sim.events.append({'type': 'beam', 'x1': self.x, 'y1': self.y,
                                   'x2': tgt.x, 'y2': tgt.y, 'color': '#FFFFFF', 'lw': 7})
        elif self.ttype == 'chaos_titan':
            sim.events.append({'type': 'boom', 'x': self.x, 'y': self.y, 'r': self.aoe, 'color': '#CC44FF'})
            for e in sim.entities:
                if not e.dead and e.fid != self.fid and _dist(e.x, e.y, self.x, self.y) < self.aoe:
                    self._hit(e, self.dmg, sim)
                    if e.type == 'unit':
                        e.confused = True
                        e.confuse_t = 2.5

    def to_dict(self):
        return {
            'id': self.id, 'type': 'titan', 'ttype': self.ttype, 'fid': self.fid,
            'x': self.x, 'y': self.y, 'hp': self.hp, 'max_hp': self.max_hp,
            'flash': self.flash, 'life': self.life, 'facing': self.facing,
        }
