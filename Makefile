.PHONY: setup run api mcp test lint typecheck ingest docker-up docker-down demo dashboard

setup:
	python -m venv .venv
	.venv/bin/pip install -e ".[dev]"

run:
	.venv/bin/uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

api:
	.venv/bin/uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

mcp:
	.venv/bin/python -m protocols.mcp_server

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

dashboard:
	.venv/bin/streamlit run dashboard/app.py
