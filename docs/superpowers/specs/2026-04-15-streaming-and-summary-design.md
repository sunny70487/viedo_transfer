# Design Spec: Real-time Subtitle Streaming + AI Summary/Chapters

**Date:** 2026-04-15
**Branch:** feature/diarization-flow
**Status:** Approved

---

## Overview

Two new features added to Whisper Transfer:

1. **Real-time subtitle streaming** — While a transcription task is still running, users can open the EditorPage and watch subtitle lines appear as each ASR segment completes.
2. **AI Summary + Chapters** — A new tab in the existing `LlmEnhanceDialog` lets users generate a text summary and a clickable timestamped chapter list from the transcript using any OpenAI-compatible LLM.

Both features depend on a third prerequisite change:

0. **Global LLM API settings** — Move Base URL / API Key / Model out of every dialog and into a single persistent settings store, accessible via a Settings icon in the Header.

---

## Sub-feature 0: Global LLM API Settings

### Problem

Every LLM-powered dialog (校對增強, 翻譯字幕, and the new 摘要) currently asks users to re-enter Base URL, API Key, and Model. This is repetitive and inconsistent.

### Solution

Store LLM credentials once in `localStorage` (key: `llm_settings`). Expose a Settings dialog from the Header. All LLM dialogs read from this store.

### Data Shape

```ts
interface LlmSettings {
  baseUrl: string   // default: 'https://api.openai.com/v1'
  apiKey: string    // default: ''
  model: string     // default: ''
}
```

### Components / Files

| File | Change |
|---|---|
| `frontend-react/src/hooks/use-llm-settings.ts` | New hook — read/write `localStorage` |
| `frontend-react/src/components/ui/LlmSettingsDialog.tsx` | New dialog — Base URL, API Key, Model (with "取得模型列表" fetch), Save button |
| `frontend-react/src/components/layout/Header.tsx` | Add `Settings` icon button next to theme toggle; opens `LlmSettingsDialog` |
| `frontend-react/src/components/editor/LlmEnhanceDialog.tsx` | Remove the three credential fields; read from `useLlmSettings()`. Show inline warning if settings are empty |

### Behaviour

- If `apiKey` is empty when a user tries to enhance/translate/summarize, show a warning: "請先點選右上角 ⚙️ 設定 LLM API" and disable the action button.
- "取得模型列表" in `LlmSettingsDialog` calls the existing `/api/llm/models` proxy endpoint.
- Settings are saved on "儲存" click and persist across sessions via `localStorage`.

---

## Sub-feature 1: Real-time Subtitle Streaming

### Problem

Transcription currently requires the full file to finish before any subtitles are visible in the EditorPage. Users cannot preview results mid-transcription.

### Approach

Extend the existing task object and SSE pipeline to carry `partial_segments` — the list of ASR segments completed so far. The EditorPage renders these in a read-only preview mode while the task is still running, then seamlessly switches to the final editable data on completion.

This approach requires zero new endpoints: the existing SSE at `/tasks/{id}/stream` already serialises the full task dict.

### Backend Changes

#### 1. `app.py` — Task model

Add one optional field:

```python
class Task(BaseModel):
    # ... existing fields ...
    partial_segments: Optional[List[Dict[str, Any]]] = None
```

This field is `None` by default and excluded from DB persistence (it is ephemeral, in-memory only).

#### 2. `backend/services/transcription_progress.py` — status callback

Extend `build_status_callback()` to return a callback that also accepts a `segment` keyword argument:

```python
def build_status_callback(task, save_task):
    def callback(message=None, progress=None, segment=None):
        if message:
            task.message = message
        if progress is not None:
            task.progress = progress
        if segment is not None:
            if task.partial_segments is None:
                task.partial_segments = []
            task.partial_segments.append(segment)
        # Do NOT save_task here — partial segments are in-memory only
        # (saves only happen at milestones to reduce DB writes)
    return callback
```

#### 3. `backend/qwen3_asr_transcribe.py` — segment callback

After each segment is appended to the internal results list, call:

```python
status_callback(segment={
    "start": seg["start"],
    "end": seg["end"],
    "text": seg["text"],
})
```

The exact hook point is inside the segment processing loop, after word-timestamp merging and text conversion are applied, so the streamed text matches what the final output will contain.

#### 4. SSE — zero changes needed

`task_api.py` already streams `task.dict()` on every change. Since `status_callback` now mutates `task.partial_segments`, the next SSE tick will include the updated list automatically.

`partial_segments` is excluded from `save_task_to_disk()` — no DB schema changes required.

### Frontend Changes

#### 1. `frontend-react/src/types/api.ts`

```ts
interface Task {
  // ... existing fields ...
  partial_segments?: Array<{
    start: number
    end: number
    text: string
    speaker?: string
  }>
}
```

#### 2. `frontend-react/src/hooks/use-task.ts` (new hook)

```ts
// Polls /tasks/{taskId} once and returns live task data via SSE
export function useTask(taskId: string): { task: Task | null; isLoading: boolean }
```

Subscribes to `/tasks/{taskId}/stream` (SSE) and keeps a local state copy of the task.

#### 3. `frontend-react/src/pages/EditorPage.tsx`

- On mount, call `useTask(taskId)` to get live task state.
- **If task is `processing` or `queued`:**
  - Render `partial_segments` as subtitle rows (read-only, no edit controls).
  - Show a sticky banner at the top of the subtitle list: `"轉錄中… 已完成 N 行"` with a spinner.
  - Toolbar buttons (save, export, enhance) are disabled.
- **When SSE emits `status: 'completed'`:**
  - Invalidate the `useSubtitles` query → reload full subtitle data.
  - Dismiss banner, enable edit controls.
- **If task is already `completed` on mount:** normal path (no change).
- **If task is `failed`:** show error banner.

#### 4. Edge cases

- If the user navigates to EditorPage for a task that doesn't exist: show 404 message (already handled by `useSubtitles`).
- `partial_segments` are not saveable — the save button remains disabled until `status === 'completed'`.
- Virtualizer (`@tanstack/react-virtual`) already handles variable-length lists; no changes needed there.

---

## Sub-feature 2: AI Summary + Chapters

### Problem

After transcription, users have no quick way to get a structured overview of the content or jump to specific topics in the video.

### Approach

Add a third tab "📋 摘要" to the existing `LlmEnhanceDialog`. The backend exposes two endpoints: one to generate and persist a notes file, one to retrieve it. The frontend renders the summary text and a clickable chapter list that seeks the VideoPlayer.

### Backend Changes

#### 1. `backend/shared/llm_postprocess.py` — `summarize_subtitles()`

```python
def summarize_subtitles(
    segments: List[Dict[str, Any]],
    *,
    api_key: str,
    base_url: str = "https://api.openai.com/v1",
    model: str = "gpt-4o-mini",
    content_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Returns:
        {
            "summary": "<paragraph>",
            "chapters": [{"time": 0.0, "title": "..."}, ...]
        }
    """
```

System prompt instructs the LLM to:
- Write a 2–4 sentence summary of the full transcript.
- Identify 3–8 topic changes and output them as a JSON array of `{time, title}` objects.
- Respond in the same language as the transcript.
- Output valid JSON only (no markdown fences).

The full transcript text (concatenated segment texts with timestamps) is passed as user message.

#### 2. `backend/services/subtitle_api.py` — two new endpoints

```
POST /api/subtitles/{task_id}/summarize
```
- Body: `{ api_key, base_url, model, content_hint? }`
- Reads subtitle JSON, calls `summarize_subtitles()`, writes `{task_id}_notes.json` to the output directory, returns the notes object.
- Returns `HTTPException(400)` if task not completed or no subtitle data.

```
GET /api/subtitles/{task_id}/notes
```
- Returns existing `{task_id}_notes.json` if present, else `404`.
- Allows the dialog to restore previously generated notes on re-open.

#### 3. `frontend-react/src/api/client.ts`

```ts
summarizeSubtitles(taskId: string, opts: LlmSummarizeRequest): Promise<SubtitleNotes>
getSubtitleNotes(taskId: string): Promise<SubtitleNotes | null>
```

#### 4. `frontend-react/src/types/api.ts`

```ts
interface SubtitleNotes {
  summary: string
  chapters: Array<{ time: number; title: string }>
}

interface LlmSummarizeRequest {
  api_key: string
  base_url: string
  model: string
  content_hint?: string
}
```

### Frontend Changes

#### 1. `LlmEnhanceDialog.tsx` — add "摘要" tab

Extend `DialogMode` type: `'enhance' | 'translate' | 'summarize'`

Tab layout (3 tabs):
```
[ ✨ 校對增強 ] [ 翻訳字幕 ] [ 📋 摘要 ]
```

**Summarize tab UI:**
- On open: call `GET /api/subtitles/{taskId}/notes`. If result exists, show it immediately (no need to re-generate).
- "開始生成" button → calls `POST /api/subtitles/{taskId}/summarize`.
- During generation: spinner + "AI 分析中…" message.
- On success:
  - **Summary block**: paragraph text in a styled card, with "複製" button.
  - **Chapters list**: each row shows `[時間碼] 章節標題` as a clickable button. Clicking calls `onSeekTo(chapter.time)` prop.
- Error state: inline error message with retry button.

#### 2. `EditorPage.tsx` — wire up `onSeekTo`

Pass `onSeekTo` to `LlmEnhanceDialog`:

```tsx
<LlmEnhanceDialog
  open={enhanceOpen}
  onClose={() => setEnhanceOpen(false)}
  subtitles={subtitles}
  taskId={taskId}
  onEnhanced={replaceSubtitles}
  onSeekTo={(time) => videoRef.current?.seek(time)}
/>
```

---

## Data Flow Summary

```
[Sub-feature 0]
Header ⚙️ → LlmSettingsDialog → localStorage(llm_settings)
                                        ↓
LlmEnhanceDialog reads via useLlmSettings()

[Sub-feature 1]
ASR engine segment done
  → status_callback(segment=seg)
    → task.partial_segments.append(seg)
      → SSE tick → task.dict() with partial_segments
        → EditorPage SSE listener
          → render partial_segments as read-only subtitles
            → on status=completed → reload full subtitle data

[Sub-feature 2]
LlmEnhanceDialog "摘要" tab
  → GET /api/subtitles/{id}/notes (check cache)
  → POST /api/subtitles/{id}/summarize
    → summarize_subtitles() → LLM → {summary, chapters}
    → write {task_id}_notes.json
    → return to frontend
      → render summary + chapter list
        → chapter click → videoRef.seek(time)
```

---

## Files Changed

### Backend
| File | Change |
|---|---|
| `backend/app.py` | Add `partial_segments` field to `Task` model; exclude from `save_task_to_disk` |
| `backend/services/transcription_progress.py` | Extend `build_status_callback` with `segment` kwarg |
| `backend/qwen3_asr_transcribe.py` | Call `status_callback(segment=...)` after each segment |
| `backend/shared/llm_postprocess.py` | Add `summarize_subtitles()` function |
| `backend/services/subtitle_api.py` | Add `POST /summarize` and `GET /notes` endpoints |

### Frontend
| File | Change |
|---|---|
| `frontend-react/src/hooks/use-llm-settings.ts` | New — localStorage read/write hook |
| `frontend-react/src/hooks/use-task.ts` | New — SSE-backed live task hook |
| `frontend-react/src/components/ui/LlmSettingsDialog.tsx` | New — global LLM credential dialog |
| `frontend-react/src/components/layout/Header.tsx` | Add Settings icon button |
| `frontend-react/src/components/editor/LlmEnhanceDialog.tsx` | Remove credential fields; add "摘要" tab; accept `onSeekTo` prop |
| `frontend-react/src/pages/EditorPage.tsx` | Handle processing state with partial preview; pass `onSeekTo` |
| `frontend-react/src/types/api.ts` | Add `partial_segments` to Task; add `SubtitleNotes`, `LlmSummarizeRequest` |
| `frontend-react/src/api/client.ts` | Add `summarizeSubtitles()`, `getSubtitleNotes()` |

---

## Out of Scope

- FunASR / Faster-Whisper engine segment streaming (only Qwen3-ASR is targeted; other engines will continue showing no partial data).
- Editing partial segments before task completes.
- Auto-generating summary on transcription completion.
- Exporting chapters to YouTube description format.
- Chapter editing / renaming.
