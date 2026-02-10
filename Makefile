.PHONY: setup run test lint typecheck ingest docker-up docker-down demo

setup:
	python -m venv .venv
	.venv/bin/pip install -e ".[dev]"

run:
	.venv/bin/uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

test:
	.venv/bin/pytest -v

lint:
	.venv/bin/ruff check .

typecheck:
	.venv/bin/mypy agent/ rag/ tools/ protocols/ api/ monitoring/

ingest:
	.venv/bin/python -m rag.ingest

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

demo:
	.venv/bin/python -m simulation.run_demo
