# Factions

A screensaver-style interactive RTS simulation. Factions battle each other autonomously across procedurally-named maps, with results rolling up through a world map, solar system, and galactic hierarchy. Watch the chaos unfold — or dig into the wiki to understand what's actually happening.

> **New here?** Check out the [Wiki](https://github.com/TheQuib/Factions/wiki) for full documentation on factions, mechanics, and how to set things up.

---

## Quick Start

### Docker (Recommended)

**Requirements:** [Docker Engine](https://docs.docker.com/engine/install/)

```bash
git clone https://github.com/TheQuib/Factions
cd Factions
touch factions.db
docker compose up -d
```

Then open your browser to [http://localhost:8000](http://localhost:8000).

To build the image locally instead of pulling it:

```bash
docker compose up -d --build
```

### Running Locally

**Requirements:** Python 3.12+

```bash
pip install -r requirements.txt
touch factions.db
./run.sh           # default port 8000
./run.sh 8001      # custom port
```

---

## What's in the Repo

| Path | Description |
|------|-------------|
| `backend/` | FastAPI server, game logic, WebSocket handling |
| `frontend/` | Browser-based game UI |
| `sprites/` | Pixel art assets for units and buildings |
| `factions.db.example` | Example SQLite database schema |
| `docker-compose.yml` | Container orchestration |
| `Dockerfile` | Container build definition |
| `Ideas.txt` | Design scratchpad and roadmap |

---

## Documentation

Full documentation lives in the [Wiki](https://github.com/TheQuib/Factions/wiki):

- [Home](https://github.com/TheQuib/Factions/wiki/Home) — Overview and navigation
- [Setup & Installation](https://github.com/TheQuib/Factions/wiki/Setup-and-Installation) — Docker and local setup
- [Game Mechanics](https://github.com/TheQuib/Factions/wiki/Game-Mechanics) — How battles, regions, heroes, and weather work
- [Factions](https://github.com/TheQuib/Factions/wiki/Factions) — All factions and their units/buildings
- [Planned Features](https://github.com/TheQuib/Factions/Issues) — What's coming next, tracked in the repository's issues

---

## Tech Stack

- **Backend:** Python 3.12, FastAPI, Uvicorn, WebSockets
- **Frontend:** HTML / JavaScript
- **Database:** SQLite
- **Infrastructure:** Docker, GitHub Actions