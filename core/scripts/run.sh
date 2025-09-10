#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH=.
venv/bin/python -m uvicorn fcore_vnext.server:app --host 127.0.0.1 --port 8767 --reload
