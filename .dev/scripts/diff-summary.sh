#!/usr/bin/env bash
# diff-summary.sh — Show what changed since last documentation sync
# Usage:
#   bash .dev/scripts/diff-summary.sh          # Show changes since last sync
#   bash .dev/scripts/diff-summary.sh --mark   # Save current HEAD as sync point
#   bash .dev/scripts/diff-summary.sh --full   # Show detailed diff
#   bash .dev/scripts/diff-summary.sh <from> <to>  # Manual commit range

set -euo pipefail

PROJECT_ROOT="$(git rev-parse --show-toplevel)"
SYNC_FILE="${PROJECT_ROOT}/.skill-sync-commit"

# --- Helper: resolve base commit ---
resolve_base() {
    if [[ -f "$SYNC_FILE" ]]; then
        cat "$SYNC_FILE"
    else
        git rev-list --max-parents=0 HEAD | head -1
    fi
}

# --- Mark current HEAD as sync point ---
if [[ "${1:-}" == "--mark" ]]; then
    git rev-parse HEAD > "$SYNC_FILE"
    echo "Sync point saved: $(cat "$SYNC_FILE")"
    exit 0
fi

# --- Resolve commit range ---
if [[ $# -ge 2 ]]; then
    BASE="$1"
    HEAD_REF="$2"
elif [[ $# -eq 1 && "$1" != "--full" ]]; then
    BASE="$1"
    HEAD_REF="HEAD"
else
    BASE="$(resolve_base)"
    HEAD_REF="HEAD"
fi

FULL_DIFF=false
if [[ "${1:-}" == "--full" || "${2:-}" == "--full" || "${3:-}" == "--full" ]]; then
    FULL_DIFF=true
fi

echo "================================================================"
echo " Documentation Sync Summary"
echo " Base: ${BASE:0:12}"
echo " Head: $(git rev-parse "${HEAD_REF}" | head -c 12)"
echo " Range: $(git rev-list --count "${BASE}..${HEAD_REF}") commits"
echo "================================================================"
echo ""

# --- Commit log ---
echo "## Recent Commits"
echo ""
git log --oneline --no-decorate "${BASE}..${HEAD_REF}" | head -30
echo ""

# --- Changed source files (excluding docs, configs, generated) ---
echo "## Changed Source Files"
echo ""
git diff --name-status "${BASE}..${HEAD_REF}" -- \
    'backend/**/*.py' \
    'frontend-react/src/**' \
    'tests/**' \
    'docker-compose.yml' \
    'Dockerfile' \
    | sort
echo ""

# --- New files ---
echo "## New Files"
echo ""
git diff --name-status --diff-filter=A "${BASE}..${HEAD_REF}" -- \
    'backend/' 'frontend-react/src/' 'tests/' \
    | sort
echo ""

# --- Deleted files ---
echo "## Deleted Files"
echo ""
git diff --name-status --diff-filter=D "${BASE}..${HEAD_REF}" -- \
    'backend/' 'frontend-react/src/' 'tests/' \
    | sort
echo ""

# --- Key files modified ---
echo "## Key Files Modified"
echo ""
KEY_FILES=(
    "backend/app.py"
    "backend/models.py"
    "backend/database.py"
    "backend/shared/engine_routing.py"
    "docker-compose.yml"
    "Dockerfile"
    "backend/requirements.txt"
    "frontend-react/package.json"
    "frontend-react/src/api/client.ts"
    "frontend-react/src/types/api.ts"
)
for f in "${KEY_FILES[@]}"; do
    if git diff --quiet "${BASE}..${HEAD_REF}" -- "$f" 2>/dev/null; then
        :
    else
        echo "  MODIFIED: $f"
    fi
done
echo ""

# --- Full diff (optional) ---
if [[ "$FULL_DIFF" == true ]]; then
    echo "## Detailed Diff"
    echo ""
    git diff --stat "${BASE}..${HEAD_REF}" -- \
        'backend/**/*.py' \
        'frontend-react/src/**' \
        'tests/**'
    echo ""
    git diff "${BASE}..${HEAD_REF}" -- \
        'backend/**/*.py' \
        'frontend-react/src/**' \
        'tests/**'
fi

echo "================================================================"
echo " To mark current HEAD as new sync point:"
echo "   bash .dev/scripts/diff-summary.sh --mark"
echo "================================================================"
