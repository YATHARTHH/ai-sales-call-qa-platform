.PHONY: help up down restart logs ps test lint typecheck smoke migrate seed build

help:
	@echo "SalesCall QA Platform — Developer Commands"
	@echo "  make up         Start all containers (Postgres, Redis, MinIO, API, Worker)"
	@echo "  make down       Stop all containers"
	@echo "  make restart    Restart all services"
	@echo "  make logs       View logs from all containers"
	@echo "  make ps         Show running container status"
	@echo "  make test       Run all unit and architecture tests"
	@echo "  make lint       Run ruff linter and code formatting check"
	@echo "  make typecheck  Run mypy static type checking"
	@echo "  make smoke      Run end-to-end async worker smoke test"
	@echo "  make accuracy   Score the engine against the labelled calibration set"
	@echo "  make seed       Seed retailers, the checklist, and the demo call"
	@echo "  make migrate    Run database migrations"
	@echo "  make build      Rebuild container images"

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose down && docker compose up -d

logs:
	docker compose logs -f

ps:
	docker compose ps

build:
	docker compose build

test:
	pytest tests/

lint:
	ruff check .

typecheck:
	mypy packages apps

smoke:
	python scripts/smoke_test.py

migrate:
	alembic upgrade head

seed:
	python scripts/seed_data.py

accuracy:
	python scripts/measure_accuracy.py
