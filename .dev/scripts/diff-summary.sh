#!/usr/bin/env bash
# diff-summary.sh — produce a compact summary of outstanding changes
# in this repository, grouped by doc-impact area.
#
# Usage:
#   .dev/scripts/diff-summary.sh [<base-ref>]
#
# Default base ref is the first of: origin/main, origin/master, HEAD.
# All file paths are relative to the repository root.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

pick_base_ref() {
    if [ -n "${1:-}" ]; then
        echo "$1"
        return
    fi
    for ref in origin/main origin/master main master; do
        if git rev-parse --verify --quiet "$ref" >/dev/null 2>&1; then
            echo "$ref"
            return
        fi
    done
    echo "HEAD"
}

BASE_REF="$(pick_base_ref "${1:-}")"

echo "=== diff-summary against ${BASE_REF} ==="
echo

# 1. Raw file list (status + path)
echo "--- changed files ---"
git diff --name-status "${BASE_REF}" -- . ':!tasks.db' ':!outputs/**' ':!uploads/**' ':!temp/**' ':!frontend-react/node_modules/**' || true
echo

# 2. Group by doc-impact area
summarize_group() {
    local label="$1"
    shift
    local files
    files="$(git diff --name-only "${BASE_REF}" -- "$@" 2>/dev/null || true)"
    if [ -n "$files" ]; then
        echo "--- ${label} ---"
        echo "$files"
        echo
    fi
}

summarize_group "backend routes/services (→ api-reference.md, function-index.md)" \
    'backend/services/**' 'backend/app.py'

summarize_group "backend shared helpers (→ function-index.md, coding-style.md)" \
    'backend/shared/**'

summarize_group "backend models (→ api-reference.md, config-reference.md)" \
    'backend/models.py' 'backend/database.py' 'backend/task_persistence.py'

summarize_group "transcription engines (→ AGENTS.md hard constraints)" \
    'backend/qwen3_asr_transcribe.py' 'backend/funasr_transcribe.py' \
    'backend/faster_whisper_transcribe.py' 'backend/shared/engine_routing.py'

summarize_group "frontend (→ AGENTS.md module map, verification step)" \
    'frontend-react/**'

summarize_group "tests (→ coding-style.md test policy)" \
    'tests/**'

summarize_group "CI / tooling (→ AGENTS.md verification, config-reference.md)" \
    '.github/**' '.flake8' 'pyproject.toml' 'requirements-dev.txt' \
    'Dockerfile' 'docker-compose.yml' 'backend/requirements.txt' \
    'frontend-react/package.json' 'frontend-react/eslint.config.js' \
    'frontend-react/vite.config.ts'

summarize_group "instruction layer (→ verify AGENTS.md and CLAUDE.md stay in sync)" \
    'AGENTS.md' 'CLAUDE.md' '.dev/**'

# 3. Integrity check: AGENTS.md must equal CLAUDE.md
echo "--- AGENTS.md vs CLAUDE.md ---"
if git diff --no-index --quiet AGENTS.md CLAUDE.md 2>/dev/null; then
    echo "identical (ok)"
else
    echo "DIFFER — reconcile before committing"
    git diff --no-index --stat AGENTS.md CLAUDE.md || true
fi
echo

# 4. Quick stat footer
echo "--- summary ---"
git diff --shortstat "${BASE_REF}" -- . ':!tasks.db' ':!outputs/**' ':!uploads/**' || true
