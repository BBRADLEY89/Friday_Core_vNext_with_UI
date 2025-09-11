.PHONY: setup core ui dev test precommit

PY=python3

setup:
	$(PY) -m pip install -r core/requirements.txt || true
	$(PY) -m pip install pre-commit ruff black mypy isort
	pre-commit install
	cd ui && npm ci || npm install

core:
	uvicorn core.app.main:app --reload --host 127.0.0.1 --port 8769

ui:
	cd ui && npm run dev

dev:
	# requires: npm i -g concurrently or use npx
	npx concurrently "make core" "make ui"

test:
	pytest -q || true
	cd ui && npm test -- --run || true

precommit:
	pre-commit run --all-files
