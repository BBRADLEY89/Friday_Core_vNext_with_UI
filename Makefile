SHELL := /bin/bash
.PHONY: neo4j-up dev-core dev-ui stop-8767 health clean-core-venv

neo4j-up:
	docker compose up -d

dev-core:
	@set -e; \
	cd core; \
	if [ ! -d .venv ]; then python3 -m venv .venv; fi; \
	source .venv/bin/activate; \
	if [ -f .env ]; then set -a; source .env; set +a; fi; \
	python -m pip install -r requirements.txt; \
	python -m uvicorn fcore_vnext.server:app --host 127.0.0.1 --port 8767

dev-ui:
	cd ui && (npm ci || npm install) && npm run dev

stop-8767:
	bash scripts/stop_port.sh 8767

health:
	curl -s http://127.0.0.1:8767/health || true

clean-core-venv:
	rm -rf core/.venv
