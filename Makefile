# Docfliq Backend — common targets
# Run from repo root: docfliq-backend/

-include .env
export

PYTHON ?= python3
VENV ?= .venv
BIN = $(VENV)/bin

# Shared package (install in editable mode for local dev)
SHARED = shared

.PHONY: venv install install-shared install-dev setup-env test lint \
	docker-up docker-down docker-clean migrate seed create-superadmin \
	run-identity run-content run-course run-webinar run-payment run-platform run-media \
	clean

## Create the virtual environment
venv:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip setuptools wheel

## Install dev tools (awscli, boto3, alembic, pytest, ruff, etc.)
install-dev: venv
	$(BIN)/pip install -r requirements-dev.txt

## Fetch RDS password from Secrets Manager and write .env (run once per machine)
setup-env:
	@bash scripts/setup-dev-env.sh

install-shared: venv
	$(BIN)/pip install -e ./$(SHARED) 2>/dev/null || $(PYTHON) -m pip install -e ./$(SHARED)

install: install-shared
	$(BIN)/pip install -r services/identity/requirements.txt 2>/dev/null || true
	$(BIN)/pip install -r services/content/requirements.txt 2>/dev/null || true
	$(BIN)/pip install -r services/course/requirements.txt 2>/dev/null || true
	$(BIN)/pip install -r services/webinar/requirements.txt 2>/dev/null || true
	$(BIN)/pip install -r services/payment/requirements.txt 2>/dev/null || true
	$(BIN)/pip install -r services/platform/requirements.txt 2>/dev/null || true
	$(BIN)/pip install -r services/media/requirements.txt 2>/dev/null || true

test:
	$(BIN)/pytest services/identity/tests services/content/tests services/course/tests \
		services/webinar/tests services/payment/tests services/platform/tests \
		services/media/tests -v --tb=short 2>/dev/null || $(PYTHON) -m pytest services/identity/tests -v --tb=short

lint:
	$(BIN)/ruff check shared services --fix 2>/dev/null || $(PYTHON) -m ruff check shared services --fix
	$(BIN)/ruff format shared services 2>/dev/null || $(PYTHON) -m ruff format shared services

## Start local postgres + redis + opensearch (plain docker run — no compose plugin needed)
docker-up:
	@docker network create docfliq-net 2>/dev/null || true
	@docker run -d --name docfliq-postgres --network docfliq-net \
		-e POSTGRES_USER=docfliq -e POSTGRES_PASSWORD=changeme \
		-p 5432:5432 \
		-v docfliq_postgres_data:/var/lib/postgresql/data \
		-v $(PWD)/scripts/init-databases.sh:/docker-entrypoint-initdb.d/init-databases.sh:ro \
		postgres:16-alpine 2>/dev/null || docker start docfliq-postgres
	@docker run -d --name docfliq-redis --network docfliq-net \
		-p 6379:6379 \
		redis:7-alpine 2>/dev/null || docker start docfliq-redis
	@docker run -d --name docfliq-opensearch --network docfliq-net \
		-e "discovery.type=single-node" \
		-e "DISABLE_SECURITY_PLUGIN=true" \
		-e "OPENSEARCH_JAVA_OPTS=-Xms256m -Xmx256m" \
		-p 9200:9200 \
		-v docfliq_opensearch_data:/usr/share/opensearch/data \
		opensearchproject/opensearch:2.11.0 2>/dev/null || docker start docfliq-opensearch
	@echo "Waiting for postgres..." && until docker exec docfliq-postgres pg_isready -U docfliq -q; do sleep 1; done
	@echo "Waiting for opensearch..." && until curl -s http://localhost:9200 >/dev/null 2>&1; do sleep 2; done
	@echo "postgres + redis + opensearch ready"

## Stop containers (data kept in volumes)
docker-down:
	@docker stop docfliq-postgres docfliq-redis docfliq-opensearch 2>/dev/null || true
	@echo "Containers stopped"

## Destroy containers + data volumes (full reset)
docker-clean:
	@docker rm -f docfliq-postgres docfliq-redis docfliq-opensearch 2>/dev/null || true
	@docker volume rm docfliq_postgres_data docfliq_opensearch_data 2>/dev/null || true
	@docker network rm docfliq-net 2>/dev/null || true
	@echo "Dev containers and data removed"

migrate:
	cd migrations/identity && $(BIN)/alembic upgrade head 2>/dev/null || true
	cd migrations/content && $(BIN)/alembic upgrade head 2>/dev/null || true
	cd migrations/course && $(BIN)/alembic upgrade head 2>/dev/null || true
	cd migrations/payment && $(BIN)/alembic upgrade head 2>/dev/null || true
	cd migrations/platform && $(BIN)/alembic upgrade head 2>/dev/null || true

seed:
	$(BIN)/python scripts/seed-data.py 2>/dev/null || $(PYTHON) scripts/seed-data.py

## Create the initial super_admin account (reads ADMIN_EMAIL / ADMIN_PASSWORD from .env)
create-superadmin:
	PYTHONPATH=services/identity:shared $(BIN)/python scripts/create_superadmin.py

run-identity:
	$(BIN)/uvicorn app.main:app --reload --app-dir services/identity --host 0.0.0.0 --port 8001

run-content:
	$(BIN)/uvicorn app.main:app --reload --app-dir services/content --host 0.0.0.0 --port 8002

run-course:
	$(BIN)/uvicorn app.main:app --reload --app-dir services/course --host 0.0.0.0 --port 8003

run-webinar:
	$(BIN)/uvicorn app.main:app --reload --app-dir services/webinar --host 0.0.0.0 --port 8004

run-payment:
	$(BIN)/uvicorn app.main:app --reload --app-dir services/payment --host 0.0.0.0 --port 8005

run-platform:
	$(BIN)/uvicorn app.main:app --reload --app-dir services/platform --host 0.0.0.0 --port 8006

run-media:
	$(BIN)/uvicorn app.main:app --reload --app-dir services/media --host 0.0.0.0 --port 8007

clean:
	rm -rf .ruff_cache .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
