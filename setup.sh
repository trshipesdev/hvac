#!/usr/bin/env bash
# One-time local setup: backend venv + deps, frontend deps, .env scaffold.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

echo "==> Backend: Python venv + dependencies"
# requirements.txt pins versions that need Python 3.10+; find the newest
# available interpreter rather than assuming `python3` is new enough (on
# macOS it's often an old system Python).
PYTHON=""
for cand in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$cand" >/dev/null; then
    ver=$("$cand" -c 'import sys; print(f"{sys.version_info[0]}{sys.version_info[1]:02d}")')
    if [ "$ver" -ge 310 ]; then PYTHON="$cand"; break; fi
  fi
done
if [ -z "$PYTHON" ]; then
  echo "No Python 3.10+ found. Install one first, e.g.:" >&2
  echo "  brew install python@3.11" >&2
  exit 1
fi
echo "Using $PYTHON ($($PYTHON --version))"
if [ ! -d backend/venv ]; then
  "$PYTHON" -m venv backend/venv
fi
backend/venv/bin/pip install --upgrade pip >/dev/null
backend/venv/bin/pip install -r backend/requirements.txt

if [ ! -f backend/.env ]; then
  cp backend/.env.example backend/.env
  echo "Created backend/.env from .env.example — fill in ANTHROPIC_API_KEY (and optionally NOAA_TOKEN) before running the app."
fi

echo "==> Backend: MongoDB"
if ! command -v mongod >/dev/null; then
  echo "mongod not found. Install it with:"
  echo "  brew tap mongodb/brew && brew install mongodb-community"
  echo "(run.sh will fail to start the database until this is installed)"
fi

echo "==> Frontend: Node dependencies"
if ! command -v node >/dev/null; then
  echo "node not found. Install Node.js first." >&2
  exit 1
fi
if ! command -v yarn >/dev/null; then
  if command -v corepack >/dev/null; then
    echo "yarn not found — enabling via corepack…"
    corepack enable
    corepack prepare yarn@1.22.22 --activate
  else
    echo "yarn not found and no corepack — installing yarn via npm…"
    npm install -g yarn
  fi
fi
(cd frontend && yarn install)

if [ ! -f frontend/.env ]; then
  cp frontend/.env.example frontend/.env
  echo "Created frontend/.env (points the UI at http://localhost:8000)."
fi

echo "==> Setup complete. Run ./run.sh to start the app."
