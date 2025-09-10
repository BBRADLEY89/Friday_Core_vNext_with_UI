.PHONY: neo4j-up dev-core dev-ui stop-8767 health

neo4j-up:
	docker compose up -d

dev-core:
	cd core && source .venv/bin/activate 2>/dev/null || python3 -m venv core/.venv && \
	. core/.venv/bin/activate && python -m pip install -r core/requirements.txt && \
	python -m uvicorn fcore_vnext.server:app --host 127.0.0.1 --port 8767

dev-ui:
	cd ui && (npm ci || npm install) && npm run dev

stop-8767:
	bash scripts/stop_port.sh 8767

health:
	curl -s http://127.0.0.1:8767/health || true

