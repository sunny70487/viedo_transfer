#!/usr/bin/env bash
# verify.sh — run the full verification suite (lint + tests + frontend).
# Exit code: 0 if everything passed, non-zero otherwise.
#
# Usage:
#   .dev/scripts/verify.sh [--backend-only|--frontend-only]
#
# Relies only on repo-local paths; resolves the repo root via git so it can be
# invoked from any subdirectory.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

MODE="${1:-all}"

run_step() {
    local label="$1"; shift
    echo "--- $label ---"
    "$@"
}

if [ "$MODE" != "--frontend-only" ]; then
    run_step "flake8" python -m flake8 \
        tests backend/shared backend/services \
        backend/models.py backend/task_persistence.py

    run_step "pytest" python -m pytest tests/ -q
fi

if [ "$MODE" != "--backend-only" ]; then
    run_step "frontend lint"  npm --prefix frontend-react run lint
    run_step "frontend build" npm --prefix frontend-react run build
fi

echo "--- verify.sh OK ---"
