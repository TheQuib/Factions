#!/bin/bash
# Start the Faction Wars server.
# Usage: ./run.sh [port]   (default port: 8000)
#
# On first run: pip install -r requirements.txt
set -e
cd "$(dirname "$0")"
PORT=${1:-8000}
echo "Starting Faction Wars on http://0.0.0.0:$PORT"
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port "$PORT" --reload
