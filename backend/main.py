"""
FastAPI server for the persistent faction war simulator.

Endpoints:
  GET  /          → serves frontend/index.html
  GET  /sprites/{name}  → serves sprites/{name}.png
  GET  /api/state → full current state (JSON, for initial page load)
  GET  /api/leaderboard → all-time faction win history
  WS   /ws        → real-time state stream (5 Hz by default)

Auth:
  Set AUTH_PASSWORD env var to enable password protection.
  Set AUTH_WHITELIST env var to a comma-separated list of IPs/CIDRs that
  bypass the password (e.g. "192.168.1.0/24,10.0.0.1").
"""
import asyncio
import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import time
from pathlib import Path

from fastapi import FastAPI, Form, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .sim.simulation import Simulation
from .sim.factions import TICK_INTERVAL, GAME_SPEED
from . import state as db

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT         = Path(__file__).parent.parent
FRONTEND_DIR = ROOT / 'frontend'
SPRITES_DIR  = ROOT / 'sprites'

# ── Frontend files ────────────────────────────────────────────────────────────
# Hash of index.html at startup — changes when a new build is deployed.
# Clients poll /api/version and prompt a refresh if it differs from what they loaded.
_FRONTEND_VERSION = hashlib.md5((FRONTEND_DIR / 'index.html').read_bytes()).hexdigest()[:12]
_LOGIN_PAGE = (FRONTEND_DIR / 'login.html').read_text()

# ── Auth config ───────────────────────────────────────────────────────────────
_AUTH_PASSWORD = os.environ.get('AUTH_PASSWORD', '')
_SESSION_COOKIE = 'factions_session'
# Derived from the password so sessions survive server restarts/redeploys.
# Falls back to a random token when no password is set (auth is disabled anyway).
_SESSION_TOKEN  = (
    hashlib.sha256(f'factions-session:{_AUTH_PASSWORD}'.encode()).hexdigest()
    if _AUTH_PASSWORD else secrets.token_hex(32)
)

_whitelist_nets: list = []
for _raw in os.environ.get('AUTH_WHITELIST', '').split(','):
    _raw = _raw.strip()
    if not _raw:
        continue
    try:
        _whitelist_nets.append(ipaddress.ip_network(_raw, strict=False))
    except ValueError:
        print(f'[auth] Ignoring invalid AUTH_WHITELIST entry: {_raw!r}')

if _AUTH_PASSWORD:
    print(f'[auth] Password protection enabled. Whitelist: {[str(n) for n in _whitelist_nets] or "none"}')


def _client_ip(request: Request) -> str:
    for header in ('X-Forwarded-For', 'X-Real-IP'):
        val = request.headers.get(header, '')
        if val:
            return val.split(',')[0].strip()
    return request.client.host if request.client else '127.0.0.1'


def _ip_allowed(ip_str: str) -> bool:
    if not _whitelist_nets:
        return False
    try:
        addr = ipaddress.ip_address(ip_str)
        return any(addr in net for net in _whitelist_nets)
    except ValueError:
        return False


def _authenticated(request: Request) -> bool:
    """Return True if the request should be allowed through without a password."""
    if not _AUTH_PASSWORD:
        return True
    if _ip_allowed(_client_ip(request)):
        return True
    return request.cookies.get(_SESSION_COOKIE) == _SESSION_TOKEN


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title='Faction Wars')


@app.middleware('http')
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    # Login page and sprites are always public
    if path in ('/login',) or path.startswith('/sprites/'):
        return await call_next(request)
    if not _authenticated(request):
        is_ws = request.headers.get('upgrade', '').lower() == 'websocket'
        if is_ws or path.startswith('/api/'):
            return Response(status_code=401)
        return RedirectResponse(url='/login', status_code=302)
    return await call_next(request)


@app.get('/login')
async def login_get():
    return HTMLResponse(_LOGIN_PAGE.replace('{error}', ''))


@app.post('/login')
async def login_post(password: str = Form(...)):
    if _AUTH_PASSWORD and hmac.compare_digest(password, _AUTH_PASSWORD):
        resp = RedirectResponse(url='/', status_code=302)
        resp.set_cookie(_SESSION_COOKIE, _SESSION_TOKEN, httponly=True, samesite='lax')
        return resp
    return HTMLResponse(
        _LOGIN_PAGE.replace('{error}', '<p class="err">INCORRECT PASSWORD</p>'),
        status_code=401,
    )

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
    prev_generation = sim.generation

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
            new_game = sim.generation != prev_generation
            payload = json.dumps(
                sim.to_state(include_terrain=new_game),
                default=str,
            )
            await _broadcast(payload)
        prev_generation = sim.generation


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


@app.get('/api/version')
async def api_version():
    """Returns a short hash of the frontend bundle. Clients poll this to detect stale pages."""
    return Response(content=_FRONTEND_VERSION, media_type='text/plain')


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
