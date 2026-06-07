"""
SQLite persistence for the simulation state.
Saves the full serialised state as a JSON blob so restarts resume where they left off.
"""
import json
import sqlite3
import os
from collections import deque

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'factions.db')


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.execute('''CREATE TABLE IF NOT EXISTS state (
        id      INTEGER PRIMARY KEY,
        payload TEXT    NOT NULL,
        saved_at REAL   NOT NULL
    )''')
    # Persistent faction win history
    c.execute('''CREATE TABLE IF NOT EXISTS wins (
        fid     TEXT NOT NULL,
        name    TEXT NOT NULL,
        won_at  REAL NOT NULL
    )''')
    c.commit()
    return c


def save_state(sim):
    """Serialise the full simulation to SQLite (overwrites the single row)."""
    import time
    payload = json.dumps(sim.to_state(include_terrain=True), default=_default)
    c = _conn()
    c.execute('DELETE FROM state')
    c.execute('INSERT INTO state (payload, saved_at) VALUES (?, ?)', (payload, time.time()))
    c.commit()
    c.close()


def load_state(sim):
    """Load last saved state into sim. Returns True on success, False if nothing saved."""
    c = _conn()
    row = c.execute('SELECT payload FROM state ORDER BY id DESC LIMIT 1').fetchone()
    c.close()
    if not row:
        return False
    try:
        data = json.loads(row[0])
        _apply_state(sim, data)
        return True
    except Exception as e:
        print(f'[state] load failed: {e}, starting fresh')
        return False


def record_win(fid, name, game_time):
    import time
    c = _conn()
    c.execute('INSERT INTO wins (fid, name, won_at) VALUES (?, ?, ?)', (fid, name, time.time()))
    c.commit()
    c.close()


def get_leaderboard(limit=10):
    c = _conn()
    rows = c.execute(
        'SELECT fid, name, COUNT(*) as wins FROM wins GROUP BY fid ORDER BY wins DESC LIMIT ?',
        (limit,)
    ).fetchall()
    c.close()
    return [{'fid': r[0], 'name': r[1], 'wins': r[2]} for r in rows]


def _default(obj):
    """JSON serialiser fallback for non-standard types."""
    return str(obj)


def _apply_state(sim, data):
    """Rebuild sim from a saved state dict. Recreates entity objects from dicts."""
    from backend.sim.entities import Castle, Unit, Building, ArrowTower, Titan
    from backend.sim.terrain import gen_terrain

    sim.game_time        = data.get('game_time', 0.0)
    sim.game_over_timer  = data.get('game_over_timer', -1.0)
    sim.winner           = data.get('winner')
    sim.titans_spawned   = data.get('titans_spawned', False)
    sim.blizzard_t       = data.get('blizzard_t', 0.0)
    sim.wildfire_zones   = data.get('wildfire_zones', [])
    sim.plague_cloud     = data.get('plague_cloud')
    sim.shake_x = sim.shake_y = sim.shake_t = 0.0
    sim.disaster_msg     = data.get('disaster_msg', '')
    sim.disaster_col     = data.get('disaster_col', '#FF8800')
    sim.disaster_t       = data.get('disaster_t', 0.0)
    sim.disaster_history = deque(data.get('disaster_history', []), maxlen=4)
    sim.next_disaster_t  = data.get('next_disaster_t', 65.0)
    sim.faction_keys     = data.get('faction_keys', [])
    sim.factions         = data.get('factions', {})
    sim.regions          = data.get('regions', [])

    # Rebuild terrain from serial
    terrain = data.get('terrain', {})
    if terrain:
        rivers_raw = terrain.get('rivers', [])
        bridges_raw = terrain.get('bridges', [])
        sim.rivers  = rivers_raw
        sim.bridges = [{'riv': rivers_raw[b['riv_idx']], 'pos': b['pos']} for b in bridges_raw]
        sim.forests = terrain.get('forests', [])
        sim.terrain_serial = terrain
    else:
        sim.rivers, sim.bridges, sim.forests = gen_terrain()
        from backend.sim.terrain import terrain_to_serializable
        sim.terrain_serial = terrain_to_serializable(sim.rivers, sim.bridges, sim.forests)

    # Rebuild entities from dicts — we reconstruct lightweight stand-ins
    sim.entities = []
    for ed in data.get('entities', []):
        etype = ed.get('type')
        if etype == 'castle':
            e = Castle(ed['x'], ed['y'], ed['fid'])
            e.hp = ed.get('hp', e.hp)
            e.gold = ed.get('gold', e.gold)
            e.desperation_active   = ed.get('desperation_active', False)
            e.desperation_cooldown = ed.get('desperation_cooldown', 0.0)
        elif etype == 'tower':
            e = ArrowTower(ed['x'], ed['y'])
            e.fid = ed.get('fid', 'neutral')
            e.hp  = ed.get('hp', e.hp)
        elif etype == 'building':
            e = Building(ed['x'], ed['y'], ed['fid'], ed['btype'])
            e.hp = ed.get('hp', e.hp)
        elif etype == 'unit':
            e = Unit(ed['x'], ed['y'], ed['fid'], ed['utype'], sim)
            e.hp = ed.get('hp', e.hp)
            e.facing = ed.get('facing', 1)
        elif etype == 'titan':
            e = Titan(ed['ttype'], ed['x'], ed['y'], ed['fid'])
            e.hp   = ed.get('hp', e.hp)
            e.life = ed.get('life', e.life)
        else:
            continue
        sim.entities.append(e)
