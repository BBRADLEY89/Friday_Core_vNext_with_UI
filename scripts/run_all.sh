#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
docker compose up -d
cd core
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn fcore_vnext.server:app --host 127.0.0.1 --port 8767

