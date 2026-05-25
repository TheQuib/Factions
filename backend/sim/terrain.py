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
            bpos = None
            for _ in range(60):
                candidate = (80 + random.random() * (MAP_W - 160) if horiz
                             else 80 + random.random() * (MAP_H - 160))

                # #32: must be 200px from any other bridge on the same river
                if any(b['riv'] is riv and abs(b['pos'] - candidate) < 200
                       for b in bridges):
                    continue

                # #33: must not land on a crossing with a perpendicular river
                at_crossing = any(
                    other['horiz'] != horiz and abs(candidate - other['pos']) < 60
                    for other in rivers if other is not riv
                )
                if at_crossing:
                    continue

                # #32: must be 120px (2-D) from any bridge on a different river
                def _bxy(b):
                    return (b['pos'], b['riv']['pos']) if b['riv']['horiz'] \
                           else (b['riv']['pos'], b['pos'])
                cxy = (candidate, riv['pos']) if horiz else (riv['pos'], candidate)
                if any(math.hypot(cxy[0] - _bxy(b)[0], cxy[1] - _bxy(b)[1]) < 120
                       for b in bridges if b['riv'] is not riv):
                    continue

                bpos = candidate
                break

            if bpos is not None:
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
    """Route around the first river that crosses the direct path.

    Two-phase approach to avoid diagonal river-edge clipping:
    - When far from the river (> ALIGN_DIST), slide laterally to line up
      with the bridge first, keeping the current perpendicular coordinate.
    - When close, aim straight through the bridge center.
    """
    ALIGN_DIST  = 60  # start lateral alignment this far from the river
    ALIGNED_TOL = 20  # consider already-aligned if within this many px of bridge axis

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
                    bx = nb['pos']
                    dist_to_river  = abs(y - r['pos'])
                    already_aligned = abs(x - bx) <= ALIGNED_TOL
                    if dist_to_river > ALIGN_DIST and not already_aligned:
                        return bx, y   # slide laterally first
                    else:
                        return bx, r['pos']  # aligned or close — head straight through
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
                    by = nb['pos']
                    dist_to_river   = abs(x - r['pos'])
                    already_aligned = abs(y - by) <= ALIGNED_TOL
                    if dist_to_river > ALIGN_DIST and not already_aligned:
                        return x, by   # slide laterally first
                    else:
                        return r['pos'], by  # aligned or close — head straight through
    return tx, ty


def terrain_to_serializable(rivers, bridges, forests):
    """Convert terrain to JSON-safe dicts (river objects use id refs for bridges)."""
    riv_list = [{'horiz': r['horiz'], 'pos': r['pos'], 'w': r['w']} for r in rivers]
    riv_index = {id(r): i for i, r in enumerate(rivers)}
    bri_list = [{'riv_idx': riv_index[id(b['riv'])], 'pos': b['pos']} for b in bridges]
    for_list = [{'x': f['x'], 'y': f['y'], 'r': f['r']} for f in forests]
    return {'rivers': riv_list, 'bridges': bri_list, 'forests': for_list}
