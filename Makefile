.DEFAULT_GOAL := help
.PHONY: help install lint typecheck test test-integration fmt run worker \
        up down logs migrate migrate-down revision psql

PY := python
COMPOSE := docker compose -f deploy/docker-compose.yml

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

install: ## Install package + dev deps
	$(PY) -m pip install -e ".[dev]"

lint: ## Run ruff
	ruff check app tests
	ruff format --check app tests

fmt: ## Auto-format with ruff
	ruff format app tests
	ruff check --fix app tests

typecheck: ## Run mypy
	mypy app

test: ## Run unit tests (no live infra)
	pytest -m "not integration"

test-integration: ## Run integration tests (needs pg + qdrant up)
	pytest -m integration

run: ## Run the API locally (reload)
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker: ## Run the background worker locally
	$(PY) -m app.worker

up: ## Start dev stack (pg + qdrant + app + worker)
	$(COMPOSE) up -d --build

down: ## Stop dev stack
	$(COMPOSE) down

logs: ## Tail dev stack logs
	$(COMPOSE) logs -f

migrate: ## Apply all migrations
	alembic -c migrations/alembic.ini upgrade head

migrate-down: ## Roll back one migration
	alembic -c migrations/alembic.ini downgrade -1

revision: ## Create a new revision (use: make revision m="message")
	alembic -c migrations/alembic.ini revision -m "$(m)"

psql: ## Open psql in the dev postgres container
	$(COMPOSE) exec postgres psql -U postgres -d ocr
