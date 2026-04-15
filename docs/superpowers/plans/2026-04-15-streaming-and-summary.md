# Streaming Subtitles + AI Summary/Chapters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (0) Move LLM credentials to a global Header settings dialog; (1) stream partial subtitle segments to EditorPage during transcription; (2) add an AI Summary + Chapters tab to LlmEnhanceDialog.

**Architecture:** `partial_segments` is appended to the in-memory Task object by the ASR engine via a new `segment` kwarg on `status_callback`; the existing SSE endpoint carries it to the frontend automatically. Summary uses the existing LLM infrastructure with a new `summarize_subtitles()` function and two new API endpoints. All LLM credential fields are extracted to a shared `use-llm-settings` hook backed by existing localStorage key.

**Tech Stack:** Python / FastAPI / Pydantic (backend), React 19 / TypeScript / Zustand / TanStack Query / Tailwind v4 (frontend), existing `whisper_llm_settings` localStorage key.

---

## Task 0: Extract LLM settings to shared hook

**Files:**
- Create: `frontend-react/src/hooks/use-llm-settings.ts`

- [ ] **Step 1: Create the hook**

```ts
// frontend-react/src/hooks/use-llm-settings.ts
import { useCallback } from 'react'

const LLM_STORAGE_KEY = 'whisper_llm_settings'

export interface LlmSettings {
  api_key: string
  base_url: string
  model: string
  content_hint: string
}

const DEFAULTS: LlmSettings = {
  api_key: '',
  base_url: 'https://api.openai.com/v1',
  model: 'gpt-4o-mini',
  content_hint: '',
}

export function loadLlmSettings(): LlmSettings {
  try {
    const raw = localStorage.getItem(LLM_STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      return {
        api_key: parsed.llm_api_key || '',
        base_url: parsed.llm_base_url || DEFAULTS.base_url,
        model: parsed.llm_model || DEFAULTS.model,
        content_hint: parsed.llm_content_hint || '',
      }
    }
  } catch { /* ignore */ }
  return { ...DEFAULTS }
}

export function saveLlmSettings(s: Partial<LlmSettings>) {
  try {
    const current = loadLlmSettings()
    const merged = { ...current, ...s }
    localStorage.setItem(LLM_STORAGE_KEY, JSON.stringify({
      llm_api_key: merged.api_key,
      llm_base_url: merged.base_url,
      llm_model: merged.model,
      llm_content_hint: merged.content_hint,
    }))
  } catch { /* ignore */ }
}

export function useLlmSettings() {
  const load = useCallback(() => loadLlmSettings(), [])
  const save = useCallback((s: Partial<LlmSettings>) => saveLlmSettings(s), [])
  return { load, save }
}
```

- [ ] **Step 2: Commit**

```
git add frontend-react/src/hooks/use-llm-settings.ts
git commit -m "feat: extract LLM settings to shared hook"
```

---

## Task 1: LlmSettingsDialog + Header settings button

**Files:**
- Create: `frontend-react/src/components/ui/LlmSettingsDialog.tsx`
- Modify: `frontend-react/src/components/layout/Header.tsx`

- [ ] **Step 1: Create LlmSettingsDialog**

```tsx
// frontend-react/src/components/ui/LlmSettingsDialog.tsx
import { useState, useEffect, useRef, useCallback } from 'react'
import { CheckCircle2, XCircle, Loader2 } from 'lucide-react'
import { Dialog } from '@/components/ui/Dialog'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { api } from '@/api/client'
import { toast } from '@/stores/toast-store'
import { loadLlmSettings, saveLlmSettings } from '@/hooks/use-llm-settings'
import type { LlmModel } from '@/types/api'

type ModelStatus = 'idle' | 'loading' | 'success' | 'error'

interface Props {
  open: boolean
  onClose: () => void
}

export function LlmSettingsDialog({ open, onClose }: Readonly<Props>) {
  const [apiKey, setApiKey] = useState('')
  const [baseUrl, setBaseUrl] = useState('https://api.openai.com/v1')
  const [model, setModel] = useState('gpt-4o-mini')
  const [models, setModels] = useState<LlmModel[]>([])
  const [modelStatus, setModelStatus] = useState<ModelStatus>('idle')
  const [modelError, setModelError] = useState('')
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!open) return
    const s = loadLlmSettings()
    setApiKey(s.api_key)
    setBaseUrl(s.base_url)
    setModel(s.model)
  }, [open])

  const fetchModels = useCallback(async (key: string, url: string) => {
    if (!key || !url) { setModels([]); setModelStatus('idle'); return }
    setModelStatus('loading')
    setModelError('')
    try {
      const data = await api.fetchLlmModels(key, url)
      setModels(data.models)
      setModelStatus('success')
    } catch (e) {
      setModelError((e as Error).message)
      setModelStatus('error')
      setModels([])
    }
  }, [])

  useEffect(() => {
    if (!open) return
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => fetchModels(apiKey, baseUrl), 800)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [open, apiKey, baseUrl, fetchModels])

  const handleSave = () => {
    saveLlmSettings({ api_key: apiKey, base_url: baseUrl, model })
    toast('success', 'LLM 設定已儲存')
    onClose()
  }

  return (
    <Dialog open={open} onClose={onClose} title="LLM API 設定">
      <div className="space-y-4">
        <p className="text-sm text-muted dark:text-muted-dark">
          設定後，AI 校對增強、翻譯字幕、摘要生成都會使用這組 API 設定。
        </p>

        <div>
          <label className="block text-sm font-medium text-text dark:text-text-dark mb-1">Base URL</label>
          <Input
            type="text"
            placeholder="https://api.openai.com/v1"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-text dark:text-text-dark mb-1">API Key</label>
          <Input
            type="password"
            placeholder="sk-..."
            autoComplete="off"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
          />
        </div>

        <div>
          <div className="flex items-center gap-2 mb-1">
            <label className="block text-sm font-medium text-text dark:text-text-dark">模型</label>
            {modelStatus === 'loading' && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted" />}
            {modelStatus === 'success' && <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />}
            {modelStatus === 'error' && (
              <span className="flex items-center gap-1 text-xs text-danger">
                <XCircle className="h-3.5 w-3.5" />
                {modelError || '連線失敗'}
              </span>
            )}
          </div>
          {models.length > 0 ? (
            <select
              className="h-10 w-full rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark px-3 text-sm text-text dark:text-text-dark focus:outline-none focus:ring-2 focus:ring-primary/50 cursor-pointer"
              value={model}
              onChange={(e) => setModel(e.target.value)}
            >
              {models.map((m) => (
                <option key={m.id} value={m.id}>{m.name}</option>
              ))}
            </select>
          ) : (
            <Input
              type="text"
              placeholder="gpt-4o-mini"
              value={model}
              onChange={(e) => setModel(e.target.value)}
            />
          )}
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" size="sm" onClick={onClose}>取消</Button>
          <Button size="sm" onClick={handleSave}>儲存設定</Button>
        </div>
      </div>
    </Dialog>
  )
}
```

- [ ] **Step 2: Add Settings button to Header**

In `frontend-react/src/components/layout/Header.tsx`, add `Settings` to imports and the new dialog:

```tsx
import { useState } from 'react'
import { AudioWaveform, Cpu, Sun, Moon, Monitor, Settings } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { LlmSettingsDialog } from '@/components/ui/LlmSettingsDialog'
import { useThemeStore } from '@/stores/theme-store'
import { useGpuInfo } from '@/hooks/use-gpu-info'

export function Header() {
  const { mode, setMode } = useThemeStore()
  const [gpuOpen, setGpuOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const gpuQuery = useGpuInfo(gpuOpen)

  const ThemeIcon = mode === 'dark' ? Moon : mode === 'light' ? Sun : Monitor

  return (
    <>
      <header className="sticky top-0 z-40 border-b border-border dark:border-border-dark bg-surface/80 dark:bg-surface-dark/80 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2 text-text dark:text-text-dark hover:opacity-80 transition-opacity">
            <AudioWaveform className="h-6 w-6 text-primary" />
            <span className="text-lg font-semibold">Whisper Transfer</span>
          </Link>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setSettingsOpen(true)}
              title="LLM API 設定"
            >
              <Settings className="h-5 w-5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setMode(mode === 'dark' ? 'light' : mode === 'light' ? 'system' : 'dark')}
              title={`主題: ${mode === 'dark' ? '深色' : mode === 'light' ? '淺色' : '系統'}`}
            >
              <ThemeIcon className="h-5 w-5" />
            </Button>
            <Button variant="outline" size="sm" onClick={() => setGpuOpen(true)}>
              <Cpu className="h-4 w-4" />
              <span className="hidden sm:inline">GPU</span>
            </Button>
          </div>
        </div>
      </header>

      <LlmSettingsDialog open={settingsOpen} onClose={() => setSettingsOpen(false)} />

      <Dialog open={gpuOpen} onClose={() => setGpuOpen(false)} title="GPU 狀態">
        {gpuQuery.isLoading ? (
          <p className="text-muted dark:text-muted-dark">載入中...</p>
        ) : gpuQuery.isError ? (
          <p className="text-danger">無法取得 GPU 資訊</p>
        ) : gpuQuery.data ? (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <span className={`h-2.5 w-2.5 rounded-full ${gpuQuery.data.available ? 'bg-success' : 'bg-danger'}`} />
              <span className="font-medium text-text dark:text-text-dark">
                {gpuQuery.data.available
                  ? `可用 (${gpuQuery.data.device_count} 裝置)`
                  : gpuQuery.data.device_count > 0
                    ? `偵測到 ${gpuQuery.data.device_count} 裝置（CUDA 未就緒）`
                    : '不可用'}
              </span>
            </div>
            {gpuQuery.data.devices.map((dev, i) => (
              <div key={i} className="rounded-lg bg-bg dark:bg-bg-dark p-3 space-y-1 text-sm">
                <p className="font-medium text-text dark:text-text-dark">{dev.name}</p>
                <p className="text-muted dark:text-muted-dark">已用: {dev.memory_allocated} / 最大: {dev.max_memory}</p>
              </div>
            ))}
          </div>
        ) : null}
      </Dialog>
    </>
  )
}
```

- [ ] **Step 3: Commit**

```
git add frontend-react/src/components/ui/LlmSettingsDialog.tsx
git add frontend-react/src/components/layout/Header.tsx
git commit -m "feat: add LLM API settings dialog in Header"
```

---

## Task 2: Simplify LlmEnhanceDialog — remove credential fields, use hook

**Files:**
- Modify: `frontend-react/src/components/editor/LlmEnhanceDialog.tsx`

Remove the `LLM_STORAGE_KEY` constant, `LlmSettings` interface, `loadSettings`, `saveSettings`, the three credential `<div>` blocks (Base URL, API Key, 模型), and the `update` callback. Replace with `loadLlmSettings()` called once on dialog open.

- [ ] **Step 1: Replace credential state with hook**

Replace the top of `LlmEnhanceDialog.tsx` up to the `fetchModels` function:

```tsx
import { useState, useEffect, useRef, useCallback } from 'react'
import { Loader2, Sparkles, Languages } from 'lucide-react'
import { Dialog } from '@/components/ui/Dialog'
import { Button } from '@/components/ui/Button'
import { api } from '@/api/client'
import { toast } from '@/stores/toast-store'
import { loadLlmSettings, saveLlmSettings } from '@/hooks/use-llm-settings'
import type { Subtitle } from '@/types/api'

const TARGET_LANGUAGES = [
  { value: '英文', label: 'English' },
  { value: '繁體中文', label: '繁體中文' },
  { value: '簡體中文', label: '简体中文' },
  { value: '日本語', label: '日本語' },
  { value: '한국어', label: '한국어' },
  { value: 'Français', label: 'Français' },
  { value: 'Deutsch', label: 'Deutsch' },
  { value: 'Español', label: 'Español' },
  { value: 'Português', label: 'Português' },
  { value: 'Italiano', label: 'Italiano' },
  { value: 'Русский', label: 'Русский' },
  { value: 'ภาษาไทย', label: 'ภาษาไทย' },
  { value: 'Tiếng Việt', label: 'Tiếng Việt' },
]

type DialogMode = 'enhance' | 'translate'

interface LlmEnhanceDialogProps {
  open: boolean
  onClose: () => void
  subtitles: Subtitle[]
  onEnhanced: (subs: Subtitle[]) => void
}
```

- [ ] **Step 2: Update component body**

Replace the component's state section (remove `settings`, `models`, `modelStatus`, `modelError`, `update`, `fetchModels` model-fetch useEffect) and add a single `contentHint` state plus one `useEffect` to read the API key for the `canEnhance` guard:

```tsx
export function LlmEnhanceDialog({ open, onClose, subtitles, onEnhanced }: Readonly<LlmEnhanceDialogProps>) {
  const [mode, setMode] = useState<DialogMode>('enhance')
  const [contentHint, setContentHint] = useState('')
  const [apiKeySet, setApiKeySet] = useState(false)
  const [enhancing, setEnhancing] = useState(false)
  const [progress, setProgress] = useState({ batch: 0, total: 0, percent: 0 })
  const [infoMsg, setInfoMsg] = useState('')
  const [targetLang, setTargetLang] = useState('英文')
  const [bilingual, setBilingual] = useState(false)

  useEffect(() => {
    if (!open) return
    const s = loadLlmSettings()
    setContentHint(s.content_hint)
    setApiKeySet(Boolean(s.api_key))
  }, [open])

  const handleEnhance = async () => {
    const s = loadLlmSettings()
    if (!s.api_key) { toast('error', '請先在右上角 ⚙️ 設定 LLM API Key'); return }
    if (subtitles.length === 0) { toast('error', '沒有字幕可供增強'); return }

    setEnhancing(true)
    setProgress({ batch: 0, total: 0, percent: 0 })
    setInfoMsg('')
    saveLlmSettings({ content_hint: contentHint })

    try {
      const stream = api.enhanceSubtitlesStream({
        subtitles: subtitles.map((s) => ({
          index: s.index,
          start_time: s.start_time,
          end_time: s.end_time,
          text: s.text,
        })),
        api_key: s.api_key,
        base_url: s.base_url,
        model: s.model,
        content_hint: contentHint || undefined,
        merge_short: mode === 'enhance',
        mode,
        target_language: mode === 'translate' ? targetLang : undefined,
        bilingual: mode === 'translate' ? bilingual : undefined,
      })

      for await (const event of stream) {
        if (event.type === 'progress') {
          setProgress({ batch: event.batch ?? 0, total: event.total ?? 0, percent: event.percent ?? 0 })
        } else if (event.type === 'info' && event.message) {
          setInfoMsg(event.message)
        } else if (event.type === 'result' && event.subtitles) {
          const enhanced: Subtitle[] = event.subtitles.map((s) => ({
            index: s.index,
            start_time: s.start_time,
            end_time: s.end_time,
            text: s.text,
          }))
          onEnhanced(enhanced)
          const merged = subtitles.length - enhanced.length
          const msg = mode === 'translate'
            ? `已翻譯 ${enhanced.length} 行字幕為${targetLang}${bilingual ? '（雙語）' : ''}`
            : merged > 0
              ? `已增強 ${enhanced.length} 行字幕（合併了 ${merged} 個過短段落）`
              : `已增強 ${enhanced.length} 行字幕`
          toast('success', msg)
          onClose()
        } else if (event.type === 'error') {
          toast('error', `增強失敗: ${event.message}`)
        }
      }
    } catch (e) {
      toast('error', `增強失敗: ${(e as Error).message}`)
    } finally {
      setEnhancing(false)
      setProgress({ batch: 0, total: 0, percent: 0 })
      setInfoMsg('')
    }
  }

  const canEnhance = apiKeySet && subtitles.length > 0
  const dialogTitle = mode === 'translate' ? 'AI 字幕翻譯' : 'AI 字幕增強'
```

- [ ] **Step 3: Update JSX — replace credential fields with settings warning**

In the JSX block, remove the three credential div blocks. Add a warning banner instead when API key is not set:

```tsx
  return (
    <Dialog open={open} onClose={onClose} title={dialogTitle}>
      <div className="space-y-4">
        {/* ... tabs and description unchanged ... */}

        {!apiKeySet && !enhancing && (
          <div className="flex items-center gap-2 rounded-lg border border-amber-300 dark:border-amber-600 bg-amber-50 dark:bg-amber-900/20 px-3 py-2 text-sm text-amber-700 dark:text-amber-400">
            <Settings className="h-4 w-4 shrink-0" />
            請先點選右上角 ⚙️ 設定 LLM API Key
          </div>
        )}

        {/* content_hint stays in the dialog */}
        {!enhancing && (
          <>
            {/* ... translate-specific fields (targetLang, bilingual) ... */}
            <div>
              <label className="block text-sm font-medium text-text dark:text-text-dark mb-1">內容描述 (選填)</label>
              <textarea
                className="w-full rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark px-3 py-2 text-sm text-text dark:text-text-dark placeholder:text-muted/60 focus:outline-none focus:ring-2 focus:ring-primary/40 resize-y min-h-[40px]"
                rows={2}
                placeholder="例如：資訊安全課程，涉及 IDA、PE、Assembly 等專業術語"
                value={contentHint}
                onChange={(e) => setContentHint(e.target.value)}
              />
            </div>
          </>
        )}

        {/* ... progress bar, action buttons unchanged ... */}
      </div>
    </Dialog>
  )
```

Note: add `Settings` to the lucide imports.

- [ ] **Step 4: Commit**

```
git add frontend-react/src/components/editor/LlmEnhanceDialog.tsx
git commit -m "refactor: move LLM credentials out of enhance dialog to global settings"
```

---

## Task 3: Backend — Task.partial_segments + extended status_callback

**Files:**
- Modify: `backend/app.py` (Task model)
- Modify: `backend/services/transcription_progress.py`
- Modify: `tests/test_transcription_progress.py`

- [ ] **Step 1: Write failing test for new callback signature**

Add to `tests/test_transcription_progress.py`:

```python
def test_build_status_callback_appends_segment_without_saving():
    task = SimpleNamespace(message="old", partial_segments=None)
    saved = []

    callback = build_status_callback(
        task=task, save_task=lambda t: saved.append("saved")
    )
    callback(segment={"start": 0.0, "end": 1.0, "text": "hello"})

    assert task.partial_segments == [{"start": 0.0, "end": 1.0, "text": "hello"}]
    # segment-only callback must NOT trigger save_task
    assert saved == []


def test_build_status_callback_segment_and_message_saves():
    task = SimpleNamespace(message="old", partial_segments=None)
    saved = []

    callback = build_status_callback(
        task=task, save_task=lambda t: saved.append("saved")
    )
    callback("new message", progress=50.0, segment={"start": 0.0, "end": 1.0, "text": "hi"})

    assert task.message == "new message"
    assert task.partial_segments == [{"start": 0.0, "end": 1.0, "text": "hi"}]
    assert saved == ["saved"]
```

- [ ] **Step 2: Run test to verify it fails**

```
cd C:\Users\cfps9\Desktop\whisper_transfer
.venv\Scripts\python -m pytest tests/test_transcription_progress.py -v
```

Expected: two new tests FAIL with `TypeError` (unexpected keyword argument).

- [ ] **Step 3: Add `partial_segments` to Task in app.py**

In `backend/app.py`, update the `Task` class:

```python
class Task(BaseModel):
    id: str
    status: str
    progress: float = 0.0
    message: str = ""
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    start_time: float
    end_time: Optional[float] = None
    source_name: Optional[str] = None
    batch_id: Optional[str] = None
    folder_id: Optional[str] = None
    sort_order: float = 0.0
    partial_segments: Optional[List[Dict[str, Any]]] = None
```

- [ ] **Step 4: Extend build_status_callback**

Replace `build_status_callback` in `backend/services/transcription_progress.py`:

```python
def build_status_callback(*, task, save_task):
    def status_callback(message=None, progress=None, segment=None):
        if message is not None:
            task.message = message
        if progress is not None:
            task.progress = progress
        if segment is not None:
            if task.partial_segments is None:
                task.partial_segments = []
            task.partial_segments.append(segment)
        # Only persist for message/progress updates, not per-segment
        if message is not None or progress is not None:
            save_task(task)

    return status_callback
```

- [ ] **Step 5: Update existing test that uses positional arg**

In `tests/test_transcription_progress.py`, the existing test passes `"new message"` positionally. Verify it still works (the new signature keeps `message` as the first positional arg). No change needed if signature is `(message=None, progress=None, segment=None)`.

- [ ] **Step 6: Run tests to verify all pass**

```
.venv\Scripts\python -m pytest tests/test_transcription_progress.py -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```
git add backend/app.py backend/services/transcription_progress.py
git add tests/test_transcription_progress.py
git commit -m "feat: add partial_segments to Task and extend status_callback"
```

---

## Task 4: Backend — Qwen3-ASR segment streaming

**Files:**
- Modify: `backend/qwen3_asr_transcribe.py`

The goal is to push each finished segment to `status_callback(segment=...)`.

**Note on streaming fidelity:**
- `split_segments=True` mode: segments stream after each audio chunk completes (true progressive streaming).
- `split_segments=False` mode: all segments are pushed once after `model.transcribe()` returns (the entire file is processed as one batch). This is still an improvement — the EditorPage will show all subtitles the moment transcription finishes, before diarization and file-writing complete.

- [ ] **Step 1: Add segment push in split_segments=True loop**

In the `split_segments` branch, after the existing `segments_json.append(seg)` line inside the inner `for seg in seg_segments:` loop (around line 565), add:

```python
                    for seg in seg_segments:
                        # ... existing accumulation code ...
                        segments_json.append(seg)
                        words_data.extend(seg.get("words", []))
                        # Stream segment to SSE
                        if status_callback:
                            status_callback(segment={
                                "start": seg.get("start", 0.0),
                                "end": seg.get("end", 0.0),
                                "text": seg.get("text", ""),
                                "speaker": seg.get("speaker"),
                            })
```

- [ ] **Step 2: Add segment push in non-split branch**

In the `else` branch (non-split), after `segments_json.extend(seg_segments)` (around line 646), add a loop:

```python
            segments_json.extend(seg_segments)
            words_data.extend(seg_words)
            # Stream all segments from this result batch
            if status_callback:
                for seg in seg_segments:
                    status_callback(segment={
                        "start": seg.get("start", 0.0),
                        "end": seg.get("end", 0.0),
                        "text": seg.get("text", ""),
                        "speaker": seg.get("speaker"),
                    })
```

- [ ] **Step 3: Verify no test regressions**

```
.venv\Scripts\python -m pytest tests/ -q
```

Expected: all existing tests PASS (the new calls are no-ops when `status_callback` is None, which is the case in all existing tests).

- [ ] **Step 4: Commit**

```
git add backend/qwen3_asr_transcribe.py
git commit -m "feat: stream partial segments via status_callback in Qwen3-ASR"
```

---

## Task 5: Frontend types + API client + useTask hook

**Files:**
- Modify: `frontend-react/src/types/api.ts`
- Modify: `frontend-react/src/api/client.ts`
- Create: `frontend-react/src/hooks/use-task.ts`

- [ ] **Step 1: Add types**

In `frontend-react/src/types/api.ts`, add `partial_segments` to `Task` and add `SubtitleNotes`:

```ts
export interface PartialSegment {
  start: number
  end: number
  text: string
  speaker?: string
}

export interface Task {
  id: string
  status: string
  progress?: number
  message?: string
  result?: TaskResult
  error?: string
  start_time?: number
  end_time?: number
  source_name?: string
  batch_id?: string
  folder_id?: string
  sort_order?: number
  partial_segments?: PartialSegment[]
}

export interface SubtitleNotes {
  summary: string
  chapters: Array<{ time: number; title: string }>
}

export interface LlmSummarizeRequest {
  api_key: string
  base_url: string
  model: string
  content_hint?: string
}
```

- [ ] **Step 2: Add API methods**

In `frontend-react/src/api/client.ts`, add after `fetchLlmModels`:

```ts
  summarizeSubtitles(taskId: string, data: LlmSummarizeRequest) {
    return request<SubtitleNotes>(`/api/subtitles/${taskId}/summarize`, {
      method: 'POST',
      body: JSON.stringify(data),
    })
  },

  getSubtitleNotes(taskId: string) {
    return fetch(`${BASE}/api/subtitles/${taskId}/notes`)
      .then(async (res) => {
        if (res.status === 404) return null
        if (!res.ok) {
          const body = await res.json().catch(() => ({}))
          throw new Error(body.detail || `Request failed: ${res.status}`)
        }
        return res.json() as Promise<SubtitleNotes>
      })
  },
```

Update the import at the top of `client.ts`:
```ts
import type {
  Task, GpuInfo, DirectoryInfo, SubdirectoryItem,
  SubtitleCollection, TranscriptionRequest,
  RetranscribeRequest, RetranscribeTask,
  BatchResponse, LlmModel, Folder, FolderUploadResponse,
  SubtitleNotes, LlmSummarizeRequest,
} from '@/types/api'
```

- [ ] **Step 3: Create useTask hook**

```ts
// frontend-react/src/hooks/use-task.ts
import { useState, useEffect, useRef } from 'react'
import type { Task } from '@/types/api'

export function useTask(taskId: string) {
  const [task, setTask] = useState<Task | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!taskId) return
    setIsLoading(true)

    // Initial fetch
    fetch(`/tasks/${taskId}`)
      .then((r) => r.ok ? r.json() : null)
      .then((data: Task | null) => {
        if (data) setTask(data)
        setIsLoading(false)
        // Only subscribe to SSE if still processing
        if (data && !['completed', 'failed'].includes(data.status)) {
          subscribeSSE()
        }
      })
      .catch(() => setIsLoading(false))

    function subscribeSSE() {
      const es = new EventSource(`/tasks/${taskId}/stream`)
      esRef.current = es
      es.onmessage = (e) => {
        try {
          const data: Task = JSON.parse(e.data)
          setTask(data)
          if (['completed', 'failed'].includes(data.status)) {
            es.close()
          }
        } catch { /* ignore */ }
      }
      es.onerror = () => es.close()
    }

    return () => {
      esRef.current?.close()
    }
  }, [taskId])

  return { task, isLoading }
}
```

- [ ] **Step 4: Commit**

```
git add frontend-react/src/types/api.ts
git add frontend-react/src/api/client.ts
git add frontend-react/src/hooks/use-task.ts
git commit -m "feat: add partial_segments types, summarize API methods, useTask hook"
```

---

## Task 6: Frontend — EditorPage streaming preview

**Files:**
- Modify: `frontend-react/src/pages/EditorPage.tsx`

When a task is still `processing` or `queued`, render `task.partial_segments` as read-only subtitle rows and show a live banner.

- [ ] **Step 1: Import useTask and wire up**

At the top of `EditorPage.tsx`, add import:

```ts
import { useTask } from '@/hooks/use-task'
```

Inside `EditorPage`, after existing state declarations:

```ts
const { task: liveTask } = useTask(taskId)

// Determine whether we're in streaming preview mode
const isStreaming = liveTask !== null && !['completed', 'failed'].includes(liveTask.status ?? '')

// When streaming, show partial segments; otherwise show saved subtitles
const displaySubtitles: Subtitle[] = isStreaming
  ? (liveTask?.partial_segments ?? []).map((seg, i) => ({
      index: i,
      start_time: seg.start,
      end_time: seg.end,
      text: seg.text,
      speaker: seg.speaker,
    }))
  : subtitles
```

- [ ] **Step 2: Add streaming banner**

In the JSX, inside the `<Card>` that holds the SubtitleToolbar, add a banner before `<SubtitleToolbar>`:

```tsx
{isStreaming && (
  <div className="flex items-center gap-2 px-4 py-2 bg-primary/10 border-b border-primary/20 text-sm text-primary">
    <Loader2 className="h-4 w-4 animate-spin shrink-0" />
    <span>
      轉錄中… 已完成 {liveTask?.partial_segments?.length ?? 0} 行
      {liveTask?.progress ? `（${Math.round(liveTask.progress)}%）` : ''}
    </span>
  </div>
)}
```

Add `Loader2` to lucide-react imports.

- [ ] **Step 3: Disable toolbar actions during streaming**

Pass `disabled` state to toolbar when streaming, and pass `displaySubtitles` to the virtualizer instead of `subtitles`:

In `SubtitleToolbar` usage:
```tsx
<SubtitleToolbar
  onSave={handleSave}
  onExport={() => setExportOpen(true)}
  onEnhance={() => setEnhanceOpen(true)}
  onImport={replaceSubtitles}
  saving={saveMutation.isPending}
  disabled={isStreaming}
/>
```

In `SubtitleToolbar.tsx`, add `disabled?: boolean` to `SubtitleToolbarProps` and pass `disabled={disabled}` to all action buttons.

Replace `subtitles` with `displaySubtitles` in the virtualizer count and row rendering.

- [ ] **Step 4: Reload subtitles when streaming completes**

```ts
const { invalidate } = useSubtitles(taskId)  // or use queryClient directly

useEffect(() => {
  if (!isStreaming && liveTask?.status === 'completed') {
    // Force reload the subtitle data from the server
    queryClient.invalidateQueries({ queryKey: ['subtitles', taskId] })
  }
}, [isStreaming, liveTask?.status, taskId])
```

Check how `useSubtitles` is defined in `hooks/use-subtitles.ts` and use its query key to invalidate. Typically:

```ts
import { useQueryClient } from '@tanstack/react-query'
const queryClient = useQueryClient()

useEffect(() => {
  if (liveTask?.status === 'completed' && subtitles.length === 0) {
    queryClient.invalidateQueries({ queryKey: ['subtitles', taskId] })
  }
}, [liveTask?.status])
```

- [ ] **Step 5: Commit**

```
git add frontend-react/src/pages/EditorPage.tsx
git add frontend-react/src/components/editor/SubtitleToolbar.tsx
git commit -m "feat: show streaming subtitle preview in EditorPage during transcription"
```

---

## Task 7: Backend — summarize_subtitles() function

**Files:**
- Modify: `backend/shared/llm_postprocess.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_llm_summarize.py`:

```python
import json
from unittest.mock import MagicMock, patch

from backend.shared.llm_postprocess import summarize_subtitles


def _make_segments():
    return [
        {"start": 0.0, "end": 5.0, "text": "大家好，今天我們要討論 Kubernetes。"},
        {"start": 5.0, "end": 10.0, "text": "首先介紹 Pod 的概念。"},
        {"start": 10.0, "end": 15.0, "text": "接下來是 Deployment 的用法。"},
    ]


def test_summarize_subtitles_returns_summary_and_chapters():
    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps({
        "summary": "本影片介紹 Kubernetes 基礎概念。",
        "chapters": [
            {"time": 0.0, "title": "簡介"},
            {"time": 5.0, "title": "Pod 概念"},
            {"time": 10.0, "title": "Deployment"},
        ]
    })

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    with patch("backend.shared.llm_postprocess.OpenAI", return_value=mock_client):
        result = summarize_subtitles(
            _make_segments(),
            api_key="test-key",
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini",
        )

    assert result["summary"] == "本影片介紹 Kubernetes 基礎概念。"
    assert len(result["chapters"]) == 3
    assert result["chapters"][0]["time"] == 0.0
    assert result["chapters"][1]["title"] == "Pod 概念"


def test_summarize_subtitles_handles_invalid_json_gracefully():
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "not json at all"

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    with patch("backend.shared.llm_postprocess.OpenAI", return_value=mock_client):
        result = summarize_subtitles(
            _make_segments(),
            api_key="test-key",
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini",
        )

    # Fallback: raw text becomes summary, empty chapters
    assert "not json" in result["summary"]
    assert result["chapters"] == []
```

- [ ] **Step 2: Run to verify it fails**

```
.venv\Scripts\python -m pytest tests/test_llm_summarize.py -v
```

Expected: FAIL — `ImportError: cannot import name 'summarize_subtitles'`.

- [ ] **Step 3: Implement summarize_subtitles()**

Add at the bottom of `backend/shared/llm_postprocess.py`:

```python
_SUMMARIZE_SYSTEM_PROMPT = """\
你是一位影片內容分析師。請根據以下字幕逐字稿，完成兩件事：

1. 撰寫一段 2-4 句的內容摘要，描述影片主題與重點。
2. 找出 3-8 個主要話題的切換點，輸出帶時間戳的章節列表。

重要規則：
- 使用與字幕相同的語言回答。
- 只輸出合法的 JSON，不要加入任何 Markdown 或解釋文字。
- 格式必須完全符合：{"summary": "...", "chapters": [{"time": 0.0, "title": "..."}, ...]}
- time 為該章節開始的秒數（浮點數）。
"""


def summarize_subtitles(
    segments: List[Dict[str, Any]],
    *,
    api_key: str,
    base_url: str = "https://api.openai.com/v1",
    model: str = "gpt-4o-mini",
    content_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Summarize a transcript and produce timestamped chapters.

    Returns:
        {"summary": str, "chapters": [{"time": float, "title": str}]}
    On error, returns {"summary": <raw LLM output or error msg>, "chapters": []}
    """
    try:
        from openai import OpenAI
    except ImportError:
        logger.error("openai package not installed — cannot summarize")
        return {"summary": "", "chapters": []}

    if not segments:
        return {"summary": "", "chapters": []}

    # Build transcript with timestamps for context
    lines = []
    for seg in segments:
        t = seg.get("start", 0.0)
        m, s = divmod(int(t), 60)
        h, m = divmod(m, 60)
        ts = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
        lines.append(f"[{ts}] {seg.get('text', '').strip()}")

    user_content = "\n".join(lines)
    if content_hint:
        user_content = f"【內容描述】{content_hint}\n\n{user_content}"

    client = OpenAI(api_key=api_key, base_url=_rewrite_localhost_url(base_url.rstrip("/")))

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SUMMARIZE_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
        )
        raw = (response.choices[0].message.content or "").strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
            if raw.endswith("```"):
                raw = raw[:-3].rstrip()
        data = json.loads(raw)
        return {
            "summary": str(data.get("summary", "")),
            "chapters": [
                {"time": float(c.get("time", 0.0)), "title": str(c.get("title", ""))}
                for c in data.get("chapters", [])
                if isinstance(c, dict)
            ],
        }
    except json.JSONDecodeError:
        logger.warning("summarize_subtitles: LLM returned non-JSON, using raw text")
        return {"summary": raw, "chapters": []}
    except Exception as exc:
        logger.error("summarize_subtitles failed: %s", exc, exc_info=True)
        raise RuntimeError(_friendly_error(exc)) from exc
```

Note: `json` is already imported at the top of the module.

- [ ] **Step 4: Run tests to verify they pass**

```
.venv\Scripts\python -m pytest tests/test_llm_summarize.py -v
```

Expected: both tests PASS.

- [ ] **Step 5: Commit**

```
git add backend/shared/llm_postprocess.py tests/test_llm_summarize.py
git commit -m "feat: add summarize_subtitles() for AI summary and chapters"
```

---

## Task 8: Backend — summarize API endpoints

**Files:**
- Modify: `backend/services/subtitle_api.py`

- [ ] **Step 1: Write smoke test**

Add to `tests/test_subtitle_api_smoke.py` (or create `tests/test_subtitle_api_summarize.py`):

```python
import json
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

# Reuse the existing fixture pattern from test_subtitle_api_smoke.py
# Import app after patching models if needed, or use the existing client setup
```

Add this minimal test at the bottom:

```python
def test_get_notes_returns_404_when_no_notes_file(client):
    """GET /api/subtitles/{task_id}/notes → 404 if notes file missing."""
    # Use a completed task that has no notes file
    response = client.get("/api/subtitles/nonexistent_task/notes")
    assert response.status_code == 404
```

- [ ] **Step 2: Add endpoints to subtitle_api.py**

At the end of `backend/services/subtitle_api.py`, before the final module code, add:

```python
class SummarizeRequest(BaseModel):
    api_key: str
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    content_hint: Optional[str] = None


@router.post("/{task_id}/summarize")
async def summarize_subtitles_endpoint(task_id: str, req: SummarizeRequest):
    """Generate summary and chapters for a task's transcript using LLM."""
    tasks = _get_task_store()
    subtitle_data = SubtitleService.load_subtitle_data(task_id, tasks)

    segments = [
        {
            "start": s.start_time,
            "end": s.end_time,
            "text": s.text,
        }
        for s in subtitle_data.subtitles
    ]

    try:
        from backend.shared.llm_postprocess import summarize_subtitles
        notes = summarize_subtitles(
            segments,
            api_key=req.api_key,
            base_url=req.base_url,
            model=req.model,
            content_hint=req.content_hint,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error("summarize failed for %s: %s", task_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="摘要生成失敗")

    # Persist notes file alongside output files
    task = tasks[task_id]
    output_dir = None
    if task.result and task.result.get("files"):
        first_file = next(iter(task.result["files"].values()), None)
        if first_file:
            output_dir = os.path.dirname(first_file)

    if output_dir:
        notes_path = os.path.join(output_dir, f"{task_id}_notes.json")
        try:
            with open(notes_path, "w", encoding="utf-8") as f:
                import json as _json
                _json.dump(notes, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("Could not save notes file: %s", e)

    return notes


@router.get("/{task_id}/notes")
async def get_subtitle_notes(task_id: str):
    """Return previously generated notes for a task, or 404 if not found."""
    tasks = _get_task_store()
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任務不存在")

    task = tasks[task_id]
    if not task.result or not task.result.get("files"):
        raise HTTPException(status_code=404, detail="找不到輸出目錄")

    first_file = next(iter(task.result["files"].values()), None)
    if not first_file:
        raise HTTPException(status_code=404, detail="找不到輸出目錄")

    output_dir = os.path.dirname(first_file)
    notes_path = os.path.join(output_dir, f"{task_id}_notes.json")

    if not os.path.isfile(notes_path):
        raise HTTPException(status_code=404, detail="尚未生成摘要")

    import json as _json
    with open(notes_path, "r", encoding="utf-8") as f:
        return _json.load(f)
```

Note: `_get_task_store()` is the existing helper in `subtitle_api.py` that returns the task registry. Check the actual function name used in the file (`_task_store` or similar) and match it.

- [ ] **Step 3: Run lint**

```
.venv\Scripts\python -m flake8 backend/services/subtitle_api.py
```

Fix any line-length issues (79 chars max).

- [ ] **Step 4: Run tests**

```
.venv\Scripts\python -m pytest tests/ -q
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```
git add backend/services/subtitle_api.py
git commit -m "feat: add POST /summarize and GET /notes subtitle API endpoints"
```

---

## Task 9: Frontend — LlmEnhanceDialog 摘要 tab + EditorPage wiring

**Files:**
- Modify: `frontend-react/src/components/editor/LlmEnhanceDialog.tsx`
- Modify: `frontend-react/src/pages/EditorPage.tsx`

- [ ] **Step 1: Add 摘要 tab to LlmEnhanceDialog**

Extend the type and add the new tab:

```tsx
import { useState, useEffect, useCallback } from 'react'
import { Sparkles, Languages, BookOpen, Copy, Check, Loader2 } from 'lucide-react'
// ... existing imports ...
import type { Subtitle, SubtitleNotes } from '@/types/api'

type DialogMode = 'enhance' | 'translate' | 'summarize'

interface LlmEnhanceDialogProps {
  open: boolean
  onClose: () => void
  subtitles: Subtitle[]
  taskId: string
  onEnhanced: (subs: Subtitle[]) => void
  onSeekTo?: (time: number) => void
}
```

Add new state for summarize:

```tsx
  const [notes, setNotes] = useState<SubtitleNotes | null>(null)
  const [summarizing, setSummarizing] = useState(false)
  const [summaryError, setSummaryError] = useState('')
  const [copied, setCopied] = useState(false)
```

Load existing notes when dialog opens in summarize mode:

```tsx
  useEffect(() => {
    if (!open || mode !== 'summarize') return
    api.getSubtitleNotes(taskId).then((n) => { if (n) setNotes(n) }).catch(() => {})
  }, [open, mode, taskId])
```

Add handleSummarize:

```tsx
  const handleSummarize = async () => {
    const s = loadLlmSettings()
    if (!s.api_key) { toast('error', '請先在右上角 ⚙️ 設定 LLM API Key'); return }

    setSummarizing(true)
    setSummaryError('')
    try {
      const result = await api.summarizeSubtitles(taskId, {
        api_key: s.api_key,
        base_url: s.base_url,
        model: s.model,
        content_hint: s.content_hint || undefined,
      })
      setNotes(result)
    } catch (e) {
      setSummaryError((e as Error).message)
    } finally {
      setSummarizing(false)
    }
  }

  const handleCopySummary = async () => {
    if (!notes?.summary) return
    await navigator.clipboard.writeText(notes.summary)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }
```

Add the third tab button in the tab row:

```tsx
            <button
              type="button"
              className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-sm font-medium transition-colors cursor-pointer ${
                mode === 'summarize'
                  ? 'bg-primary text-white'
                  : 'text-text dark:text-text-dark hover:bg-gray-50 dark:hover:bg-gray-800'
              }`}
              onClick={() => setMode('summarize')}
            >
              <BookOpen className="h-3.5 w-3.5" />
              摘要
            </button>
```

Add summarize tab body (placed in the conditional rendering area, alongside existing enhance/translate content):

```tsx
        {mode === 'summarize' && !summarizing && (
          <div className="space-y-3">
            {summaryError && (
              <p className="text-sm text-danger">{summaryError}</p>
            )}
            {notes ? (
              <>
                <div className="relative rounded-lg border border-border dark:border-border-dark bg-bg dark:bg-bg-dark p-3">
                  <p className="text-sm text-text dark:text-text-dark leading-relaxed pr-8">{notes.summary}</p>
                  <button
                    type="button"
                    onClick={handleCopySummary}
                    className="absolute top-2 right-2 p-1 rounded text-muted hover:text-text dark:hover:text-text-dark"
                    title="複製摘要"
                  >
                    {copied ? <Check className="h-3.5 w-3.5 text-success" /> : <Copy className="h-3.5 w-3.5" />}
                  </button>
                </div>
                {notes.chapters.length > 0 && (
                  <div className="space-y-1">
                    <p className="text-xs font-medium text-muted dark:text-muted-dark uppercase tracking-wider">章節</p>
                    {notes.chapters.map((ch, i) => {
                      const m = Math.floor(ch.time / 60)
                      const s = Math.floor(ch.time % 60)
                      const ts = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
                      return (
                        <button
                          key={i}
                          type="button"
                          onClick={() => onSeekTo?.(ch.time)}
                          className="flex items-center gap-2 w-full text-left px-2 py-1.5 rounded hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors group"
                        >
                          <span className="font-mono text-xs text-primary shrink-0">{ts}</span>
                          <span className="text-sm text-text dark:text-text-dark group-hover:text-primary transition-colors">{ch.title}</span>
                        </button>
                      )
                    })}
                  </div>
                )}
                <Button variant="outline" size="sm" onClick={handleSummarize} className="w-full">
                  重新生成
                </Button>
              </>
            ) : (
              <Button size="sm" onClick={handleSummarize} className="w-full" disabled={!apiKeySet}>
                <BookOpen className="h-4 w-4" />
                開始生成摘要
              </Button>
            )}
          </div>
        )}

        {mode === 'summarize' && summarizing && (
          <div className="flex items-center gap-2 py-4 justify-center text-sm text-muted dark:text-muted-dark">
            <Loader2 className="h-4 w-4 animate-spin" />
            AI 分析中…
          </div>
        )}
```

- [ ] **Step 2: Update action button — hide for summarize mode**

Wrap the existing action button (取消 + 開始增強/翻譯) in a condition: only show when `mode !== 'summarize'`. The summarize tab has its own internal buttons.

```tsx
        {mode !== 'summarize' && (
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" size="sm" onClick={onClose} disabled={enhancing}>取消</Button>
            <Button size="sm" onClick={handleEnhance} disabled={!canEnhance || enhancing} loading={enhancing}>
              {/* ... existing button content ... */}
            </Button>
          </div>
        )}
        {mode === 'summarize' && (
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" size="sm" onClick={onClose}>關閉</Button>
          </div>
        )}
```

- [ ] **Step 3: Wire up in EditorPage.tsx**

Update the `LlmEnhanceDialog` call site:

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

- [ ] **Step 4: Build and verify no TypeScript errors**

```
cd C:\Users\cfps9\Desktop\whisper_transfer\frontend-react
npm run build 2>&1 | tail -20
```

Expected: Build succeeds with no type errors.

- [ ] **Step 5: Commit**

```
git add frontend-react/src/components/editor/LlmEnhanceDialog.tsx
git add frontend-react/src/pages/EditorPage.tsx
git commit -m "feat: add AI summary and chapters tab to LlmEnhanceDialog"
```

---

## Task 10: Final checks

- [ ] **Step 1: Run full backend test suite**

```
cd C:\Users\cfps9\Desktop\whisper_transfer
.venv\Scripts\python -m pytest tests/ -q
```

Expected: all tests PASS.

- [ ] **Step 2: Run lint**

```
.venv\Scripts\python -m flake8 backend/shared/llm_postprocess.py backend/services/subtitle_api.py backend/services/transcription_progress.py backend/app.py
```

Fix any issues.

- [ ] **Step 3: Frontend type check**

```
cd frontend-react
npx tsc --noEmit
```

Fix any type errors.

- [ ] **Step 4: Final commit**

```
git add -A
git commit -m "chore: final lint and type fixes for streaming + summary features"
```
