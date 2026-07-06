# Makefile — dev environment entry point for macOS / Linux / WSL.
# Windows users: use .\scripts\dev-setup.ps1 instead.
#
# All targets resolve paths relative to the Makefile's directory so they can
# be invoked from any subdirectory: `make -C /path/to/repo setup`.

PYTHON ?= python
NPM    ?= npm
FRONTEND_DIR := frontend-react

.PHONY: help setup dev test lint check clean

help:
	@echo "whisper_transfer — dev targets"
	@echo "  make setup   Install backend + frontend deps (idempotent)"
	@echo "  make dev     Start backend (:5000) and frontend (:5173) concurrently"
	@echo "  make test    Run pytest suite"
	@echo "  make lint    Run flake8 (CI scope) + frontend ESLint"
	@echo "  make check   lint + test (local CI simulation)"
	@echo "  make clean   Remove caches and build artifacts (keeps outputs/ and uploads/)"

setup:
	@echo "--- environment ---"
	@$(PYTHON) --version
	@$(NPM) --version
	@test -f .env || { \
		if [ -f .env.example ]; then \
			cp .env.example .env; \
			echo "Created .env from .env.example"; \
		fi; \
	}
	@echo "--- backend deps ---"
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r backend/requirements.txt
	$(PYTHON) -m pip install -r requirements-dev.txt
	@echo "--- frontend deps ---"
	$(NPM) --prefix $(FRONTEND_DIR) install
	@echo ""
	@echo "Setup complete. Next: make dev  or  make check"

dev:
	@echo "Starting backend (:5000) and frontend (:5173) — Ctrl+C to stop both."
	@trap 'kill 0' INT TERM; \
	 $(PYTHON) -m uvicorn backend.app:app --host 0.0.0.0 --port 5000 --reload & \
	 $(NPM) --prefix $(FRONTEND_DIR) run dev & \
	 wait

test:
	$(PYTHON) -m pytest tests/ -q

lint:
	$(PYTHON) -m flake8 tests backend/shared backend/services \
		backend/models.py backend/task_persistence.py
	$(NPM) --prefix $(FRONTEND_DIR) run lint

check: lint test
	@echo "--- check OK ---"

clean:
	@echo "--- remove python caches ---"
	@find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \) \
		-not -path './.venv/*' -not -path './node_modules/*' \
		-exec rm -rf {} + 2>/dev/null || true
	@echo "--- remove frontend build artifacts ---"
	@rm -rf $(FRONTEND_DIR)/dist
	@echo "--- clear temp/ contents (outputs/ and uploads/ intentionally preserved) ---"
	@if [ -d temp ]; then find temp -mindepth 1 -delete 2>/dev/null || true; fi
	@echo "--- clean OK ---"
