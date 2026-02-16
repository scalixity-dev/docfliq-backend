# Docfliq Backend — common targets
# Run from repo root: docfliq-backend/

PYTHON ?= python3
VENV ?= .venv
BIN = $(VENV)/bin

# Shared package (install in editable mode for local dev)
SHARED = shared

.PHONY: install install-shared test lint docker-up migrate seed \
	run-identity run-content run-course run-webinar run-payment run-platform \
	clean

install-shared:
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

docker-up:
	docker-compose up -d postgres redis

migrate:
	cd migrations/identity && $(BIN)/alembic upgrade head 2>/dev/null || true
	cd migrations/content && $(BIN)/alembic upgrade head 2>/dev/null || true
	cd migrations/course && $(BIN)/alembic upgrade head 2>/dev/null || true
	cd migrations/payment && $(BIN)/alembic upgrade head 2>/dev/null || true
	cd migrations/platform && $(BIN)/alembic upgrade head 2>/dev/null || true

seed:
	$(BIN)/python scripts/seed-data.py 2>/dev/null || $(PYTHON) scripts/seed-data.py

run-identity:
	cd services/identity && $(BIN)/uvicorn app.main:app --reload --host 0.0.0.0 --port 8001 2>/dev/null || cd services/identity && $(PYTHON) -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8001

run-content:
	cd services/content && $(BIN)/uvicorn app.main:app --reload --host 0.0.0.0 --port 8002 2>/dev/null || cd services/content && $(PYTHON) -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8002

run-course:
	cd services/course && $(BIN)/uvicorn app.main:app --reload --host 0.0.0.0 --port 8003 2>/dev/null || cd services/course && $(PYTHON) -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8003

run-webinar:
	cd services/webinar && $(BIN)/uvicorn app.main:app --reload --host 0.0.0.0 --port 8004 2>/dev/null || cd services/webinar && $(PYTHON) -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8004

run-payment:
	cd services/payment && $(BIN)/uvicorn app.main:app --reload --host 0.0.0.0 --port 8005 2>/dev/null || cd services/payment && $(PYTHON) -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8005

run-platform:
	cd services/platform && $(BIN)/uvicorn app.main:app --reload --host 0.0.0.0 --port 8006 2>/dev/null || cd services/platform && $(PYTHON) -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8006

clean:
	rm -rf .ruff_cache .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
