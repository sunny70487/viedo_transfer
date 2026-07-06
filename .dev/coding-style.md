# Coding Style

## Pre-Commit Checklist

Run these (in order) before every commit. They must all pass.

```
python -m flake8 tests backend/shared backend/services backend/models.py backend/task_persistence.py
python -m pytest tests/ -q
npm --prefix frontend-react run lint
npm --prefix frontend-react run build
```

Additional manual checks:

- No secrets in diff (`git diff --cached`).
- New imports resolve against `backend/requirements.txt` or `frontend-react/package.json`.
- New files follow the naming tables below.
- New endpoints have a matching `tests/test_*.py` case.
- If the `Task` model changed, update `TaskRecord` in `backend/database.py` and add a migration in `_run_migrations`.

## Naming — Real Examples

| Kind | Convention | Real example |
|---|---|---|
| Python file | `snake_case.py` | `backend/services/transcription_launcher.py` |
| Python function | verb-first `snake_case` | `resolve_output_directory(*, request, task_id, output_root)` |
| Private helper | leading underscore | `_detect_max_workers()` in `backend/app.py` |
| Module singleton | leading underscore | `_transcription_executor` in `backend/app.py` |
| Pydantic class | `<Domain><Role>` | `RetranscribeRequest`, `SubtitleSearchRequest` in `backend/models.py` |
| Service class | `PascalCase` | `RetranscribeService` in `backend/services/retranscribe_service.py` |
| Constant set | `UPPER_SNAKE_CASE` | `FUNASR_MODEL_NAMES` in `backend/shared/engine_routing.py` |
| TS component file | `PascalCase.tsx` | `frontend-react/src/components/editor/SubtitleRow.tsx` |
| TS hook file | `use-kebab-case.ts` | `frontend-react/src/hooks/use-task-stream.ts` |
| TS store file | `<name>-store.ts` | `frontend-react/src/stores/editor-store.ts` |
| Zustand store hook | `use<Pascal>Store` | `useEditorStore` |
| Test file | `test_<module>.py` | `tests/test_transcription_progress.py` |

Keyword-only arguments are preferred for any public helper with 3+ parameters:

```python
# backend/services/transcription_progress.py
def estimate_total_steps(
    *,
    split_segments,
    segment_duration,
    file_path,
    get_duration,
    get_file_size_mb,
):
    ...
```

## Error Handling — Real Examples

```python
# 1. API boundary validation → HTTPException
# backend/services/task_api.py:27
if task_id not in tasks:
    raise HTTPException(status_code=404, detail="任務不存在")

# 2. Validation helpers → (bool, error_msg) tuple
# backend/services/upload_preprocessing.py:8
def validate_upload_filename(filename: str):
    if not filename:
        return False, "未提供文件名"
    ...
    return True, None

# 3. Worker-level broad except with full logger context
# backend/app.py:373
except Exception as e:
    logger.error(f"任務 {task_id} 失敗: {str(e)}", exc_info=True)
    finalize_task_failure(task=task, error=e, now=time.time())
    save_task_to_disk(task)

# 4. Non-fatal paths use logger.warning and swallow
# backend/app.py:350
except Exception as llm_err:
    logger.warning("LLM enhancement failed (non-fatal): %s", llm_err)

# 5. Precondition failures raise RuntimeError from helpers
# backend/services/url_preprocessing.py:14
if not downloaded_file:
    raise RuntimeError("下載失敗")
```

Rules of thumb:
- Raise `HTTPException` only in route handlers or helpers that are always called from them.
- In background workers, always log the exception with `exc_info=True` before updating task state.
- Do not catch `Exception` in pure helpers — let the caller decide.

## Logging Guide

Logging is configured once in `backend/app.py`:

```python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("whisper_app.log")],
)
```

Per-module pattern:

```python
import logging
logger = logging.getLogger("my_module")
```

Level matrix:

| Level | When to use | Example |
|---|---|---|
| DEBUG | Frequent, low-value diagnostic | `logger.debug(f"任務 {task_id} 已保存到資料庫")` |
| INFO | Lifecycle events | `logger.info("Batch %s created with %d URL task(s)", batch_id, len(ids))` |
| WARNING | Non-fatal degradation | `logger.warning("LLM enhancement failed (non-fatal): %s", err)` |
| ERROR | Caught exception, always pair with `exc_info=True` | `logger.error("Failed to list folders: %s", e, exc_info=True)` |

Both `%s` placeholders and f-strings are accepted; prefer `%s` in hot paths.

## Test Writing Guide

Location: `tests/` (flat, no nesting).
Naming: `test_<module_under_test>.py`, function `test_<behavior_in_words>()`.

Common ingredients:

```python
# Lightweight stub objects
from types import SimpleNamespace
task = SimpleNamespace(status="processing", message="", partial_segments=None)

# Patch module-level attributes (engine, SessionLocal, etc.)
monkeypatch.setattr(task_persistence_module, "SessionLocal", test_session)

# Import isolation for modules with startup side effects
import importlib, sys
sys.modules.pop("backend.services.subtitle_api", None)
subtitle_api = importlib.import_module("backend.services.subtitle_api")

# HTTP testing
from fastapi import FastAPI
from fastapi.testclient import TestClient
app = FastAPI()
app.include_router(router)
client = TestClient(app)
```

Policy:
- Every new public function in `backend/services/` or `backend/shared/` ships with at least one test.
- Prefer `SimpleNamespace` to full Pydantic models when testing pure functions — it matches the attribute-access style the code uses.
- For persistence, use an in-memory SQLite created via `create_engine(f"sqlite:///{tmp_path}/test.db")` and patch `SessionLocal`.
- Do not share state between test files; there is no `conftest.py`.

## File Templates

### Python service module

```python
"""<module purpose — one line>"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException

logger = logging.getLogger("my_api")

router = APIRouter(prefix="/api/my", tags=["my"])

_registry: Optional[Dict[str, Any]] = None


def set_my_registry(reg: Dict[str, Any]) -> None:
    global _registry
    _registry = reg


def _get_registry() -> Dict[str, Any]:
    if _registry is None:
        raise RuntimeError("my_api 未初始化")
    return _registry


@router.get("/{item_id}")
async def read_item(item_id: str):
    reg = _get_registry()
    if item_id not in reg:
        raise HTTPException(status_code=404, detail="找不到項目")
    return reg[item_id]
```

### Python shared helper

```python
"""<helper purpose — one line>"""

import logging

logger = logging.getLogger(__name__)


def compute_something(*, value: int, factor: int = 2) -> int:
    if value < 0:
        raise ValueError("value must be non-negative")
    return value * factor
```

### Test template

```python
from types import SimpleNamespace

from backend.services.my_module import compute_something


def test_compute_something_doubles_by_default():
    assert compute_something(value=5) == 10


def test_compute_something_rejects_negative():
    import pytest
    with pytest.raises(ValueError):
        compute_something(value=-1)
```

### React hook template

```ts
// frontend-react/src/hooks/use-my-thing.ts
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'

export function useMyThing(id: string) {
  return useQuery({
    queryKey: ['my-thing', id],
    queryFn: () => api.getMyThing(id),
    enabled: !!id,
  })
}
```

### Zustand store template

```ts
// frontend-react/src/stores/my-store.ts
import { create } from 'zustand'

interface MyState {
  count: number
  increment: () => void
}

export const useMyStore = create<MyState>()((set) => ({
  count: 0,
  increment: () => set((s) => ({ count: s.count + 1 })),
}))
```
