import random
import math
from .factions import MAP_W, MAP_H, STARTS


def gen_terrain():
    rivers, bridges, forests = [], [], []
    margin = 160

    n_riv = 2 + random.randint(0, 1)
    attempts = 0
    while len(rivers) < n_riv and attempts < 40:
        attempts += 1
        horiz = random.random() < 0.5
        pos = (margin + random.random() * (MAP_H - margin * 2) if horiz
               else margin + random.random() * (MAP_W - margin * 2))
        ok = True
        for r in rivers:
            if abs(r['pos'] - pos) < 200:
                ok = False
        for s in STARTS:
            d = abs(s[1] - pos) if horiz else abs(s[0] - pos)
            if d < 130:
                ok = False
        if not ok:
            continue
        riv = {'horiz': horiz, 'pos': pos, 'w': 26}
        rivers.append(riv)
        for _ in range(2):
            bpos, ba = None, 0
            while ba < 30:
                bpos = (80 + random.random() * (MAP_W - 160) if horiz
                        else 80 + random.random() * (MAP_H - 160))
                if not any(b['riv'] is riv and abs(b['pos'] - bpos) < 200 for b in bridges):
                    break
                ba += 1
            bridges.append({'riv': riv, 'pos': bpos})

    n_for = 4 + random.randint(0, 2)
    attempts = 0
    while len(forests) < n_for and attempts < 60:
        attempts += 1
        fx = 80 + random.random() * (MAP_W - 160)
        fy = 80 + random.random() * (MAP_H - 160)
        fr = 55 + random.random() * 35
        ok = True
        for s in STARTS:
            if math.hypot(s[0] - fx, s[1] - fy) < 160:
                ok = False
        for f in forests:
            if math.hypot(f['x'] - fx, f['y'] - fy) < 120:
                ok = False
        if ok:
            forests.append({'x': fx, 'y': fy, 'r': fr})

    return rivers, bridges, forests


def on_bridge(x, y, bridges):
    for b in bridges:
        r = b['riv']
        if r['horiz']:
            if abs(y - r['pos']) <= r['w'] / 2 + 2 and abs(x - b['pos']) <= 28:
                return True
        else:
            if abs(x - r['pos']) <= r['w'] / 2 + 2 and abs(y - b['pos']) <= 28:
                return True
    return False


def in_river(x, y, rivers, bridges):
    for r in rivers:
        if r['horiz']:
            if abs(y - r['pos']) <= r['w'] / 2 and not on_bridge(x, y, bridges):
                return True
        else:
            if abs(x - r['pos']) <= r['w'] / 2 and not on_bridge(x, y, bridges):
                return True
    return False


def in_forest(x, y, forests):
    return any(math.hypot(x - f['x'], y - f['y']) <= f['r'] for f in forests)


def terrain_speed(x, y, rivers, bridges, river_bonus=False):
    if in_river(x, y, rivers, bridges):
        return 1.4 if river_bonus else 0.18
    return 1.0


def get_waypoint(x, y, tx, ty, rivers, bridges):
    """Route around the first river that crosses the direct path."""
    for r in rivers:
        if r['horiz']:
            min_y, max_y = min(y, ty), max(y, ty)
            if min_y <= r['pos'] <= max_y:
                nb, nd = None, float('inf')
                for b in bridges:
                    if b['riv'] is r:
                        d = math.hypot(b['pos'] - x, r['pos'] - y)
                        if d < nd:
                            nd, nb = d, b
                if nb:
                    return nb['pos'], r['pos']
        else:
            min_x, max_x = min(x, tx), max(x, tx)
            if min_x <= r['pos'] <= max_x:
                nb, nd = None, float('inf')
                for b in bridges:
                    if b['riv'] is r:
                        d = math.hypot(r['pos'] - x, b['pos'] - y)
                        if d < nd:
                            nd, nb = d, b
                if nb:
                    return r['pos'], nb['pos']
    return tx, ty


def terrain_to_serializable(rivers, bridges, forests):
    """Convert terrain to JSON-safe dicts (river objects use id refs for bridges)."""
    riv_list = [{'horiz': r['horiz'], 'pos': r['pos'], 'w': r['w']} for r in rivers]
    riv_index = {id(r): i for i, r in enumerate(rivers)}
    bri_list = [{'riv_idx': riv_index[id(b['riv'])], 'pos': b['pos']} for b in bridges]
    for_list = [{'x': f['x'], 'y': f['y'], 'r': f['r']} for f in forests]
    return {'rivers': riv_list, 'bridges': bri_list, 'forests': for_list}
