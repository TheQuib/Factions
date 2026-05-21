"""
FastAPI server for the persistent faction war simulator.

Endpoints:
  GET  /          → serves frontend/index.html
  GET  /sprites/{name}  → serves sprites/{name}.png
  GET  /api/state → full current state (JSON, for initial page load)
  GET  /api/leaderboard → all-time faction win history
  WS   /ws        → real-time state stream (5 Hz by default)
"""
import asyncio
import json
import os
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .sim.simulation import Simulation
from .sim.factions import TICK_INTERVAL, GAME_SPEED
from . import state as db

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT         = Path(__file__).parent.parent
FRONTEND_DIR = ROOT / 'frontend'
SPRITES_DIR  = ROOT / 'sprites'

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title='Faction Wars')

# Serve sprites/ as static files
app.mount('/sprites', StaticFiles(directory=str(SPRITES_DIR)), name='sprites')

# ── Simulation (single global instance) ───────────────────────────────────────
sim = Simulation()
_state_loaded = db.load_state(sim)
if _state_loaded:
    print('[server] Resumed from saved state')
else:
    print('[server] Starting fresh simulation')

# ── WebSocket hub ─────────────────────────────────────────────────────────────
_clients: set[WebSocket] = set()


async def _broadcast(payload: str):
    dead = set()
    for ws in _clients:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.add(ws)
    _clients.difference_update(dead)


# ── Simulation loop task ──────────────────────────────────────────────────────
_save_interval = 30.0   # real-seconds between SQLite saves
_last_save     = time.monotonic()


async def sim_loop():
    global _last_save
    dt = TICK_INTERVAL * GAME_SPEED   # game-seconds per tick
    prev_winner = sim.winner

    while True:
        await asyncio.sleep(TICK_INTERVAL)

        sim.tick(dt)

        # Record wins
        if sim.winner and sim.winner != prev_winner and sim.winner != 'draw':
            fname = sim.factions.get(sim.winner, {}).get('name', sim.winner)
            db.record_win(sim.winner, fname, sim.game_time)
        prev_winner = sim.winner

        # Periodic save
        now = time.monotonic()
        if now - _last_save >= _save_interval:
            _last_save = now
            db.save_state(sim)

        # Broadcast to clients if any are connected
        if _clients:
            payload = json.dumps(sim.to_state(), default=str)
            await _broadcast(payload)


@app.on_event('startup')
async def startup():
    asyncio.create_task(sim_loop())


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get('/')
async def index():
    return FileResponse(str(FRONTEND_DIR / 'index.html'))


@app.get('/api/state')
async def api_state():
    """Full state including terrain — used by clients on first connect."""
    return JSONResponse(sim.to_state(include_terrain=True))


@app.get('/api/leaderboard')
async def api_leaderboard():
    return JSONResponse(db.get_leaderboard())


@app.post('/api/reset')
async def api_reset():
    """Immediately restart the simulation and push fresh state to all clients."""
    sim.init_game()
    db.save_state(sim)
    if _clients:
        payload = json.dumps(
            {**sim.to_state(include_terrain=True), 'full': True},
            default=str)
        await _broadcast(payload)
    return JSONResponse({'ok': True})


@app.websocket('/ws')
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _clients.add(ws)
    # Send full state (with terrain) immediately so the client can render
    try:
        await ws.send_text(json.dumps(
            {**sim.to_state(include_terrain=True), 'full': True},
            default=str))
        while True:
            # Keep the connection alive; sending is handled by sim_loop
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _clients.discard(ws)
