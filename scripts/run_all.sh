#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

docker compose up -d  # optional, safe if no compose

cd core
python3 -m venv .venv
source .venv/bin/activate
if [ -f .env ]; then set -a; source .env; set +a; fi
python -m pip install -r requirements.txt
python -m uvicorn fcore_vnext.server:app --host 127.0.0.1 --port 8767
