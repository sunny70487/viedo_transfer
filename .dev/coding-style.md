# Coding Style Guide

## Pre-Commit Checklist

1. [ ] Code passes `flake8` with default settings (line length 79)
2. [ ] New functions have type hints on parameters and return values
3. [ ] Error paths log with `logger.error(msg, exc_info=True)`
4. [ ] New API endpoints return proper HTTP status codes via `HTTPException`
5. [ ] Pydantic models use `Field(...)` with descriptions for API-facing fields
6. [ ] Tests added for new logic in `tests/test_<module>.py`
7. [ ] TypeScript types mirror backend Pydantic models in `types/api.ts`
8. [ ] No hardcoded absolute paths — use `Path(__file__).resolve().parent` or env vars

## Python Naming (with real examples)

### Functions
```python
# Public API functions — descriptive verb phrases
def create_task_entry(*, tasks, save_task, source_name, batch_id=None):
def validate_upload_filename(filename: str):
def transcribe_audio(**kwargs):
def build_status_callback(*, task, save_task):
def finalize_task_success(*, task, transcription_results, output_directory, now):

# Private helpers — leading underscore
def _detect_max_workers() -> int:
def _apply_llm_enhancement(transcription_results, request, status_callback):
def _rewrite_localhost_url(url: str) -> str:
def _find_video_path(task) -> Optional[str]:
```

### Classes
```python
class SubtitleCollection(BaseModel):
class TaskPersistence:          # Static-method-only utility class
class RetranscribeService:      # Stateful service with ThreadPoolExecutor
class SubtitleConverter:        # Stateless converter
class TaskStore:                # Thin wrapper around dict
```

### Constants
```python
SUPPORTED_MEDIA_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
FUNASR_MODEL_NAMES = frozenset({...})
MAX_WORKERS = _detect_max_workers()
_MAX_LINES_PER_BATCH = 80      # Module-private constant
_BATCH_COOLDOWN = 1.0
```

### Variables
```python
task_id = str(uuid.uuid4())
output_directory = resolve_output_directory(...)
subtitle_collection = SubtitleService.load_subtitle_data(task_id, tasks)
```

## TypeScript Naming (with real examples)

### Files and components
```
frontend-react/src/stores/editor-store.ts    # kebab-case for non-component files
frontend-react/src/components/editor/SubtitleRow.tsx  # PascalCase for components
frontend-react/src/hooks/use-tasks.ts        # use-kebab-case for hooks
frontend-react/src/lib/utils.ts              # kebab-case for utilities
```

### Types and interfaces
```typescript
export interface SubtitleCollection { task_id: string; subtitles: Subtitle[]; ... }
export interface TranscriptionRequest { url?: string; model_size?: string; ... }
```

### State stores (Zustand)
```typescript
export const useEditorStore = create<EditorState>()((set, get) => ({
  subtitles: [],
  setSubtitles: (subs) => { ... },
  updateSubtitle: (index, update) => { ... },
}))
```

## Error Handling Patterns

### Route handler (standard pattern)
```python
@router.get("/{task_id}")
async def get_subtitles(task_id: str):
    tasks = get_tasks_storage()
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任務不存在")
    # ... business logic ...
```

### Service method with cleanup
```python
try:
    result = do_work()
    task.status = "completed"
except Exception as e:
    logger.error(f"操作失敗: {str(e)}", exc_info=True)
    task.status = "failed"
    task.error = str(e)
finally:
    cleanup_temp_files()
```

### Background worker (process_transcription pattern)
```python
def process_transcription(task_id, file_path, request):
    task = tasks[task_id]
    try:
        # ... do work, update task.progress along the way ...
        finalize_task_success(task=task, ...)
        save_task_to_disk(task)
    except Exception as e:
        logger.error(f"任務 {task_id} 失敗: {str(e)}", exc_info=True)
        finalize_task_failure(task=task, error=e, now=time.time())
        save_task_to_disk(task)
```

### Frontend API error handling
```typescript
async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...init })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || body.error || `Request failed: ${res.status}`)
  }
  return res.json()
}
```

## Logging Guide

```python
import logging
logger = logging.getLogger("my_module")

# Operation start/completion
logger.info("Task %s submitted (pool active ≈ %d)", task_id, len(executor._threads))

# Non-fatal issues
logger.warning("LLM enhancement failed (non-fatal): %s", err)

# Failures — always include exc_info
logger.error(f"任務 {task_id} 失敗: {str(e)}", exc_info=True)

# Verbose debugging (persistence layer)
logger.debug(f"任務 {task_id} 已保存到資料庫")
```

## Test Writing Guide

### File naming
```
tests/test_<module_name>.py
```

### Test structure (pytest)
```python
import pytest
from pydantic import ValidationError
from backend.models import Subtitle

def test_subtitle_strips_surrounding_whitespace():
    subtitle = Subtitle(index=0, start_time=0.0, end_time=1.5, text="  測試  ")
    assert subtitle.text == "測試"

def test_subtitle_rejects_whitespace_only_text():
    with pytest.raises(ValidationError, match="字幕文字不能為空"):
        Subtitle(index=0, start_time=0.0, end_time=1.5, text="   ")
```

### Mocking pattern (for service tests)
```python
from unittest.mock import MagicMock, patch

def test_create_task_entry():
    tasks = {}
    save = MagicMock()
    task = create_task_entry(tasks=tasks, save_task=save, source_name="test.mp3")
    assert task.id in tasks
    save.assert_called_once()
```

### Running tests
```bash
python -m pytest tests/ -q          # All tests
python -m pytest tests/test_models.py -v  # Single file, verbose
```

## Adding Dependencies

### Python (backend)
1. Add to `backend/requirements.txt` with minimum version: `package>=x.y.z`
2. Platform-specific: use PEP 508 markers: `pywin32>=305; platform_system=="Windows"`
3. Docker: if the package needs special CUDA handling, add install step in `Dockerfile`

### Node.js (frontend)
```bash
cd frontend-react && npm install <package>
```

## File Templates

### New service file (`backend/services/my_service.py`)
```python
import logging
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException

logger = logging.getLogger("my_service")
router = APIRouter(prefix="/api/myservice", tags=["myservice"])

_registry: Optional[Dict[str, Any]] = None

def set_registry(tasks: Dict[str, Any]) -> None:
    global _registry
    _registry = tasks

@router.get("/{item_id}")
async def get_item(item_id: str):
    if _registry is None:
        raise RuntimeError("Registry not initialized")
    # ... implementation ...
```

### New test file (`tests/test_my_service.py`)
```python
import pytest

def test_my_feature_basic():
    # Arrange
    # Act
    # Assert
    pass
```
