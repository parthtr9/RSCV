.PHONY: dev-mock can-up record stop test lint fmt typecheck clean

# ── Mock mode (no hardware) ──────────────────────────────────────────────────
dev-mock:
	@echo "Starting mock stack..."
	sudo modprobe vcan 2>/dev/null || true
	sudo ip link add dev vcan0 type vcan 2>/dev/null || true
	sudo ip link set vcan0 up 2>/dev/null || true
	MOCK=1 python -m hardware.mock_can --interface vcan0 &
	MOCK=1 uvicorn api.main:app --reload --port 8000 &
	cd dashboard && npm run dev

# ── Real hardware ────────────────────────────────────────────────────────────
can-up:
	sudo ip link set can0 type can \
		bitrate 1000000 dbitrate 5000000 fd on \
		sample-point 0.75 dsample-point 0.75
	sudo ip link set can0 up
	sudo ip link set can0 txqueuelen 1000
	@ip -details link show can0

record:
	uvicorn api.main:app --port 8000 &
	@echo "POST /record/start to begin episode"

stop:
	@echo "POST /record/stop to finalize episode"

# ── Dev / CI ─────────────────────────────────────────────────────────────────
test:
	pytest

test-cov:
	pytest --cov=. --cov-report=term-missing

lint:
	ruff check .

fmt:
	ruff format .

typecheck:
	mypy hardware cameras recording api

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
	rm -rf .mypy_cache .ruff_cache .pytest_cache htmlcov
