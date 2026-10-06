# ---------------------------------------------------------------------------
# Civil Registry & Family Tree
#
#   make help     list the targets
#   make up       start the database and the API
# ---------------------------------------------------------------------------

SHELL := /bin/bash
.DEFAULT_GOAL := help

BACKEND  := backend
FRONTEND := frontend
COMPOSE  := docker compose
PY       := $(BACKEND)/.venv/bin/python
PIP      := $(BACKEND)/.venv/bin/pip
TEST_DB  := civil_registry_test

# Local-only overrides (.env.local is git-ignored and holds real secrets).
-include $(BACKEND)/.env.local
export

.PHONY: help
help: ## show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Local development (no Docker)
# ---------------------------------------------------------------------------
.PHONY: install
install: ## create the virtualenv and install backend dependencies
	python3 -m venv $(BACKEND)/.venv
	$(PIP) install --upgrade pip
	$(PIP) install -r $(BACKEND)/requirements-dev.txt

.PHONY: db-up
db-up: ## start a local PostgreSQL for development (docker, no app)
	$(COMPOSE) up -d db

.PHONY: test-db
test-db: ## create the pytest database if it does not exist yet
	$(COMPOSE) exec -T db psql -U $${POSTGRES_USER:-civil} -d postgres -tc \
		"SELECT 1 FROM pg_database WHERE datname='$(TEST_DB)'" | grep -q 1 \
		|| $(COMPOSE) exec -T db psql -U $${POSTGRES_USER:-civil} -d postgres \
			-c "CREATE DATABASE $(TEST_DB)"

.PHONY: migrate
migrate: ## apply the Alembic migrations to the development database
	cd $(BACKEND) && .venv/bin/alembic upgrade head

.PHONY: seed
seed: ## load sample_civil_registry.sql and create the bootstrap admin
	cd $(BACKEND) && .venv/bin/python scripts/seed.py --file ../sample_civil_registry.sql

.PHONY: dev
dev: ## run the API with autoreload
	cd $(BACKEND) && .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

.PHONY: test
test: ## run the backend test suite
	cd $(BACKEND) && .venv/bin/python -m pytest tests/

.PHONY: test-cov
test-cov: ## run the backend test suite with a coverage report
	cd $(BACKEND) && .venv/bin/python -m pytest tests/ --cov=app --cov-report=term-missing

.PHONY: lint
lint: ## ruff + black in check mode
	cd $(BACKEND) && .venv/bin/ruff check app tests scripts alembic && .venv/bin/black --check app tests scripts alembic

.PHONY: format
format: ## apply ruff fixes and black formatting
	cd $(BACKEND) && .venv/bin/ruff check app tests scripts alembic --fix && .venv/bin/black app tests scripts alembic

# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------
.PHONY: install-fe
install-fe: ## install the frontend dependencies
	cd $(FRONTEND) && npm install

.PHONY: dev-fe
dev-fe: ## run the Vite dev server (proxies /api to the local API)
	cd $(FRONTEND) && npm run dev

.PHONY: lint-fe
lint-fe: ## lint the frontend
	cd $(FRONTEND) && npm run lint

.PHONY: build-fe
build-fe: ## typecheck and build the frontend bundle
	cd $(FRONTEND) && npm run build

.PHONY: check-fe
check-fe: lint-fe build-fe ## frontend lint + typecheck + build

.PHONY: check
check: lint test ## lint and test

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------
.PHONY: build
build: ## build the container images
	$(COMPOSE) build

.PHONY: up
up: ## start the full stack in the background
	$(COMPOSE) up -d --build
	@echo "UI:       http://localhost:$${FRONTEND_PORT:-8090}"
	@echo "API docs: http://localhost:$${BACKEND_PORT:-8000}/docs"

.PHONY: down
down: ## stop the stack (keeps volumes)
	$(COMPOSE) down

.PHONY: clean
clean: ## stop the stack and delete its volumes
	$(COMPOSE) down -v

.PHONY: logs
logs: ## follow the container logs
	$(COMPOSE) logs -f

.PHONY: shell
shell: ## open a psql shell on the application database
	$(COMPOSE) exec db psql -U $${POSTGRES_USER:-civil} -d $${POSTGRES_DB:-civil_registry}

.PHONY: psql
psql: ## open a psql shell on the development database (local stack)
	psql -h localhost -p $${POSTGRES_PORT:-5432} -U $${POSTGRES_USER:-civil} -d $${POSTGRES_DB:-civil_registry}

.PHONY: migrate-docker
migrate-docker: ## apply migrations inside the running backend container
	$(COMPOSE) exec backend alembic upgrade head

.PHONY: seed-docker
seed-docker: ## load the sample data inside the running backend container
	$(COMPOSE) exec backend python scripts/seed.py --file /app/sample_civil_registry.sql

.PHONY: secret
secret: ## print a strong SECRET_KEY to paste into .env
	@python3 -c "import secrets; print(secrets.token_urlsafe(64))"

.PHONY: env
env: ## create .env from .env.example with a freshly generated SECRET_KEY
	@if [ -f .env ]; then echo ".env already exists - not overwriting it"; exit 1; fi
	@sed "s|^SECRET_KEY=.*|SECRET_KEY=$$(python3 -c 'import secrets; print(secrets.token_urlsafe(64))')|" \
		.env.example > .env
	@echo "created .env with a random SECRET_KEY (keep it out of git)"

# ---------------------------------------------------------------------------
# Housekeeping
# ---------------------------------------------------------------------------
.PHONY: clean-venv
clean-venv: ## delete the virtualenv, caches and test uploads
	rm -rf $(BACKEND)/.venv $(BACKEND)/.test-uploads
	find $(BACKEND) -type d -name __pycache__ -prune -exec rm -rf {} +