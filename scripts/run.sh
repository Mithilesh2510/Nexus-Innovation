#!/usr/bin/env bash
# Starts the FastAPI backend and a static file server for the frontend.
# Usage: bash scripts/run.sh
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "== Healthcare Supply Chain Intelligence =="
echo "Project root: $ROOT_DIR"

# 1. Generate data if it doesn't exist yet
if [ ! -f "$ROOT_DIR/data/medicines.csv" ]; then
  echo "-- Generating synthetic dataset..."
  python3 "$ROOT_DIR/data/generate_data.py"
fi

# 2. Sync / migrate to MySQL if configured
echo "-- Verifying MySQL database status..."
python3 "$ROOT_DIR/scripts/migrate_to_mysql.py" || echo "[WARN] MySQL migration skipped or encountered an error; backend will fall back to CSV if needed."

# 3. Start the backend
echo "-- Starting FastAPI backend on http://localhost:8000 (docs at /docs)"
cd "$ROOT_DIR/backend"
uvicorn main:app --reload --port 8000 &
BACKEND_PID=$!

# 4. Serve the frontend as static files
echo "-- Serving frontend on http://localhost:5500"
cd "$ROOT_DIR/frontend"
python3 -m http.server 5500 &
FRONTEND_PID=$!

echo ""
echo "Backend:  http://localhost:8000/docs"
echo "Frontend: http://localhost:5500"
echo ""
echo "Press Ctrl+C to stop both servers."

trap "kill $BACKEND_PID $FRONTEND_PID" EXIT
wait
