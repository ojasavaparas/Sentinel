.PHONY: setup run api mcp test lint typecheck ingest docker-up docker-down demo dashboard infra-deploy infra-destroy ecr-push deploy

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

infra-deploy:
	cd infra && cdk deploy

infra-destroy:
	cd infra && cdk destroy

ecr-push:
	$(eval ACCOUNT_ID := $(shell aws sts get-caller-identity --query Account --output text))
	$(eval REGION := $(or $(AWS_REGION),us-east-1))
	$(eval ECR_URI := $(ACCOUNT_ID).dkr.ecr.$(REGION).amazonaws.com/sentinel)
	aws ecr get-login-password --region $(REGION) | docker login --username AWS --password-stdin $(ACCOUNT_ID).dkr.ecr.$(REGION).amazonaws.com
	docker build -t sentinel:latest .
	docker tag sentinel:latest $(ECR_URI):latest
	docker push $(ECR_URI):latest

deploy:
	./scripts/deploy.sh
