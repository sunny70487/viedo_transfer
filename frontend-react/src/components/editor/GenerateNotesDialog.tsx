import { useCallback, useEffect, useRef, useState } from 'react'
import { Check, Copy, Download, FileText, ListChecks, RefreshCw, Settings, Square } from 'lucide-react'
import { Dialog } from '@/components/ui/Dialog'
import { Button } from '@/components/ui/Button'
import { api } from '@/api/client'
import { toast } from '@/stores/toast-store'
import { loadLlmSettings, saveLlmSettings } from '@/hooks/use-llm-settings'
import { createPool } from '@/lib/run-pool'
import { NoteRenderer } from '@/components/editor/notes/NoteRenderer'
import { ChapterPicker } from '@/components/editor/notes/ChapterPicker'
import { ReferenceInput } from '@/components/editor/notes/ReferenceInput'
import { ChapterNoteSection, type ChapterRuntime } from '@/components/editor/notes/ChapterNoteSection'
import {
  chaptersToGenerate, defaultSelection, excludedSections,
} from '@/components/editor/notes/chapter-selection'
import type { NoteReferences, StudyNotesState } from '@/types/api'

const MAX_PARALLEL_CHAPTERS = 3
const PLAN_KEY = 'plan'
const API_KEY_HINT = '請先在右上角 ⚙ 設定 LLM API Key'
const LOGISTICS_HINT = '課程行政與閒談'

const EMPTY_STATE: StudyNotesState = {
  markdown: '',
  outline: null,
  draft_outline: null,
  chapters: [],
  references: { text: '', sources: [], used_chars: 0, truncated: false },
}

const EMPTY_RUNTIME: ChapterRuntime = {
  status: null, streamed: '', error: '', markdown: null, fresh: false,
}

function isAbort(error: unknown): boolean {
  return typeof error === 'object' && error !== null
    && 'name' in error && error.name === 'AbortError'
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

interface GenerateNotesDialogProps {
  open: boolean
  onClose: () => void
  taskId: string
  hasSubtitles: boolean
}

export function GenerateNotesDialog({
  open, onClose, taskId, hasSubtitles,
}: Readonly<GenerateNotesDialogProps>) {
  return (
    <Dialog open={open} onClose={onClose} title="產生筆記" className="max-w-3xl">
      <NotesDialogBody key={taskId} taskId={taskId} hasSubtitles={hasSubtitles} />
    </Dialog>
  )
}

/** Mounted only while the dialog is open, so every open starts from the saved state. */
function NotesDialogBody({ taskId, hasSubtitles }: Readonly<{ taskId: string; hasSubtitles: boolean }>) {
  const [settings] = useState(loadLlmSettings)
  const [contentHint, setContentHint] = useState(settings.content_hint)
  const [notes, setNotes] = useState<StudyNotesState | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)
  const [override, setOverride] = useState<'intro' | 'planning' | null>(null)
  const [selected, setSelected] = useState<Set<string> | null>(null)
  const [refText, setRefText] = useState('')
  const [working, setWorking] = useState(false)
  const [runtime, setRuntime] = useState<Record<string, ChapterRuntime>>({})
  const [busyCount, setBusyCount] = useState(0)
  const [syncing, setSyncing] = useState(false)
  const [copied, setCopied] = useState(false)

  const [pool] = useState(() => createPool(MAX_PARALLEL_CHAPTERS))
  const aliveRef = useRef(true)
  const controllersRef = useRef(new Map<string, AbortController>())
  const busyRef = useRef(new Set<string>())

  useEffect(() => {
    aliveRef.current = true
    let cancelled = false
    const controllers = controllersRef.current
    api.getStudyNotes(taskId)
      .then((state) => {
        if (cancelled) return
        setNotes(state)
        setRefText(state?.references.text ?? '')
        setLoadError('')
      })
      .catch((e: unknown) => { if (!cancelled) setLoadError(errorMessage(e)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => {
      cancelled = true
      aliveRef.current = false
      pool.clear()
      controllers.forEach((controller) => controller.abort())
    }
  }, [taskId, pool, reloadKey])

  const patch = useCallback((chapterId: string, change: Partial<ChapterRuntime>) => {
    if (!aliveRef.current) return
    setRuntime((prev) => ({
      ...prev,
      [chapterId]: { ...(prev[chapterId] ?? EMPTY_RUNTIME), ...change },
    }))
  }, [])

  // Copy/download use the note as assembled by the server (overview, chapter
  // order, reference list), so it is fetched again once generation settles.
  const refreshAssembled = useCallback(() => {
    setSyncing(true)
    api.getStudyNotes(taskId)
      .then((state) => {
        if (!aliveRef.current || !state) return
        setNotes((prev) => (prev ? { ...prev, markdown: state.markdown, chapters: state.chapters } : state))
      })
      .catch((e: unknown) => {
        if (aliveRef.current) toast('error', `無法更新完整筆記，複製與下載的內容可能不是最新的: ${errorMessage(e)}`)
      })
      .finally(() => { if (aliveRef.current) setSyncing(false) })
  }, [taskId])

  const enqueue = useCallback((chapterId: string) => {
    const busy = busyRef.current
    if (busy.has(chapterId)) return
    busy.add(chapterId)
    setBusyCount(busy.size)
    patch(chapterId, { status: 'queued', error: '' })

    pool.run(async () => {
      const s = loadLlmSettings()
      const controller = new AbortController()
      controllersRef.current.set(chapterId, controller)
      patch(chapterId, { status: 'generating', streamed: '' })
      try {
        const stream = api.generateChapterNoteStream(taskId, chapterId, {
          api_key: s.api_key,
          base_url: s.base_url,
          model: s.model,
          content_hint: s.content_hint || undefined,
        }, controller.signal)
        let settled = false
        for await (const event of stream) {
          if (!aliveRef.current) return
          if (event.type === 'delta') {
            setRuntime((prev) => {
              const current = prev[chapterId] ?? EMPTY_RUNTIME
              return { ...prev, [chapterId]: { ...current, streamed: current.streamed + event.text } }
            })
          } else if (event.type === 'done') {
            // One update: the final markdown, streaming off and `fresh` must
            // arrive together, because animation cards read `fresh` on mount.
            settled = true
            patch(chapterId, { status: null, streamed: '', error: '', markdown: event.markdown, fresh: true })
          } else {
            settled = true
            patch(chapterId, { status: 'failed', streamed: '', error: event.message })
          }
        }
        if (!settled) patch(chapterId, { status: 'failed', streamed: '', error: '連線中斷，請重試' })
      } finally {
        controllersRef.current.delete(chapterId)
      }
    }).catch((e: unknown) => {
      if (isAbort(e)) patch(chapterId, { status: null, streamed: '' })
      else patch(chapterId, { status: 'failed', streamed: '', error: errorMessage(e) })
    }).finally(() => {
      busy.delete(chapterId)
      if (!aliveRef.current) return
      setBusyCount(busy.size)
      if (busy.size === 0) refreshAssembled()
    })
  }, [taskId, pool, patch, refreshAssembled])

  const stopChapters = () => {
    pool.clear()
    controllersRef.current.forEach((controller, key) => {
      if (key !== PLAN_KEY) controller.abort()
    })
  }

  const handlePlan = async () => {
    const s = loadLlmSettings()
    if (!s.api_key) { toast('error', API_KEY_HINT); return }
    if (!hasSubtitles) { toast('error', '目前沒有字幕資料'); return }

    saveLlmSettings({ content_hint: contentHint })
    const controller = new AbortController()
    controllersRef.current.set(PLAN_KEY, controller)
    setOverride('planning')
    try {
      const { outline } = await api.planNotesOutline(taskId, {
        api_key: s.api_key,
        base_url: s.base_url,
        model: s.model,
        content_hint: contentHint || undefined,
      }, controller.signal)
      if (!aliveRef.current) return
      setNotes((prev) => ({ ...(prev ?? EMPTY_STATE), draft_outline: outline }))
      setSelected(null)
      setOverride(null)
    } catch (e) {
      if (!aliveRef.current) return
      if (!isAbort(e)) toast('error', `章節規劃失敗: ${errorMessage(e)}`)
      setOverride('intro')
    } finally {
      controllersRef.current.delete(PLAN_KEY)
    }
  }

  const handleDiscard = async () => {
    setWorking(true)
    try {
      await api.discardNotesOutline(taskId)
      if (!aliveRef.current) return
      setNotes((prev) => (prev ? { ...prev, draft_outline: null } : prev))
      setSelected(null)
    } catch (e) {
      toast('error', `無法放棄規劃: ${errorMessage(e)}`)
    } finally {
      if (aliveRef.current) setWorking(false)
    }
  }

  const handleStart = async (chapterIds: string[], excluded: string[]) => {
    if (!loadLlmSettings().api_key) { toast('error', API_KEY_HINT); return }
    if (!notes) return
    setWorking(true)
    try {
      await api.saveNoteReferences(taskId, {
        text: refText,
        urls: notes.references.sources.map((source) => source.url),
      })
      const state = await api.startChapterNotes(taskId, excluded)
      if (!aliveRef.current) return
      setNotes(state)
      setRefText(state.references.text)
      setRuntime({})
      setSelected(null)
      setOverride(null)
      chapterIds.forEach(enqueue)
    } catch (e) {
      toast('error', `無法開始產生: ${errorMessage(e)}`)
    } finally {
      if (aliveRef.current) setWorking(false)
    }
  }

  const handleCopy = async () => {
    if (!notes?.markdown) return
    try {
      await navigator.clipboard.writeText(notes.markdown)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (e) {
      toast('error', `複製失敗: ${errorMessage(e)}`)
    }
  }

  const handleDownload = () => {
    if (!notes?.markdown) return
    const blob = new Blob([notes.markdown], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `notes_${taskId}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  const setReferences = (references: NoteReferences) => {
    setNotes((prev) => ({ ...(prev ?? EMPTY_STATE), references }))
  }

  if (loading) {
    return (
      <p className="py-8 text-center text-sm text-muted dark:text-muted-dark animate-pulse" aria-busy="true">
        載入筆記中…
      </p>
    )
  }

  if (loadError) {
    return (
      <div className="space-y-3 py-4">
        <p role="alert" className="text-sm text-danger">無法載入筆記：{loadError}</p>
        <div className="flex justify-end">
          <Button variant="outline" size="sm" onClick={() => { setLoading(true); setReloadKey((n) => n + 1) }}>
            <RefreshCw className="h-4 w-4" />
            重新載入
          </Button>
        </div>
      </div>
    )
  }

  const apiKeySet = Boolean(settings.api_key)
  const canGenerate = apiKeySet && hasSubtitles
  const draft = notes?.draft_outline ?? null
  const outline = notes?.outline ?? null
  const hasNote = Boolean(outline || notes?.markdown)
  const savedView = draft ? 'draft' : outline ? 'notes' : notes?.markdown ? 'legacy' : 'intro'
  const view = override ?? savedView
  const references = notes?.references ?? EMPTY_STATE.references

  const draftChapters = draft?.chapters ?? []
  const chosen = selected ?? defaultSelection(draftChapters)
  const chosenIds = chaptersToGenerate(draftChapters, chosen)
  const noteChapters = notes?.chapters ?? []
  const writtenCount = noteChapters.filter((c) => runtime[c.id]?.markdown ?? c.markdown).length
  const exportDisabled = busyCount > 0 || syncing || !notes?.markdown

  const exportButtons = (
    <>
      <Button variant="outline" size="sm" onClick={() => void handleCopy()} disabled={exportDisabled}>
        {copied ? <Check className="h-4 w-4 text-green-500" /> : <Copy className="h-4 w-4" />}
        {copied ? '已複製' : '複製'}
      </Button>
      <Button variant="outline" size="sm" onClick={handleDownload} disabled={exportDisabled}>
        <Download className="h-4 w-4" />
        下載 .md
      </Button>
    </>
  )

  return (
    <div className="space-y-4">
      {!apiKeySet && (
        <div
          role="alert"
          className="flex items-center gap-2 rounded-lg border border-amber-300 dark:border-amber-600 bg-amber-50 dark:bg-amber-900/20 px-3 py-2 text-sm text-amber-700 dark:text-amber-400"
        >
          <Settings className="h-4 w-4 shrink-0" aria-hidden="true" />
          請先點選右上角 ⚙ 設定 LLM API Key
        </div>
      )}

      {view === 'intro' && (
        <>
          <p className="text-sm text-muted dark:text-muted-dark">
            先讀完整份逐字稿，把談同一主題的內容整合成章，並把作業、評分、考試這類課程行政與閒談分開；你勾選要的章節後，每章各寫成一篇有脈絡的繁體中文教學筆記（比喻、表格、Mermaid/ASCII 圖），並為重點概念繪製 SVG 動畫。
          </p>
          <div>
            <label htmlFor="notes-hint" className="block text-sm font-medium text-text dark:text-text-dark mb-1">
              內容描述 <span className="text-muted dark:text-muted-dark font-normal">（選填）</span>
            </label>
            <textarea
              id="notes-hint"
              className="w-full rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark px-3 py-2 text-sm text-text dark:text-text-dark placeholder:text-muted/60 focus:outline-none focus:ring-2 focus:ring-primary/40 resize-y min-h-[40px]"
              rows={2}
              placeholder="例如：資訊安全課程，涉及 IDA、PE、Assembly 等專業術語"
              value={contentHint}
              onChange={(e) => setContentHint(e.target.value)}
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            {savedView !== 'intro' && (
              <Button variant="outline" size="sm" onClick={() => setOverride(null)}>取消</Button>
            )}
            <Button size="sm" onClick={() => void handlePlan()} disabled={!canGenerate}>
              <ListChecks className="h-4 w-4" />
              開始產生
            </Button>
          </div>
        </>
      )}

      {view === 'planning' && (
        <>
          <div className="py-6 text-center" aria-live="polite" aria-busy="true">
            <p className="text-sm font-medium text-text dark:text-text-dark animate-pulse">正在閱讀逐字稿並規劃章節…</p>
            <p className="mt-1 text-xs text-muted dark:text-muted-dark">
              影片越長需要越久，完成後會列出預計產生的章節讓你勾選。
            </p>
          </div>
          <div className="flex justify-end pt-2">
            <Button variant="outline" size="sm" onClick={() => controllersRef.current.get(PLAN_KEY)?.abort()}>
              <Square className="h-4 w-4" />
              停止
            </Button>
          </div>
        </>
      )}

      {view === 'draft' && draft && (
        <>
          <div>
            <h3 className="break-words text-base font-semibold text-text dark:text-text-dark">{draft.title}</h3>
            {draft.overview && (
              <p className="mt-1 break-words text-sm text-muted dark:text-muted-dark">{draft.overview}</p>
            )}
          </div>
          <p className="text-sm text-muted dark:text-muted-dark">
            {draft.grouped
              ? '談同一主題的小節已整合成一章，同一章只會寫成一篇連貫的筆記。可以取消整章，或只取消其中的小節。'
              : '這次沒能依主題整合小節，以下每個小節各成一章。想要整合的話，可以放棄這次規劃後重新規劃。'}
            {draftChapters.some((chapter) => chapter.kind === 'logistics')
              && `「${LOGISTICS_HINT}」預設不寫進筆記。`}
          </p>
          <ChapterPicker chapters={draftChapters} selected={chosen} onChange={setSelected} disabled={working} />
          <ReferenceInput
            taskId={taskId}
            references={references}
            text={refText}
            onTextChange={setRefText}
            onChange={setReferences}
            disabled={working}
          />
          {hasNote && (
            <p role="alert" className="rounded-lg border border-amber-300 dark:border-amber-600 bg-amber-50 dark:bg-amber-900/20 px-3 py-2 text-sm text-amber-700 dark:text-amber-400">
              產生後會取代現有的筆記與概念動畫。
            </p>
          )}
          <div className="flex flex-wrap justify-end gap-2 pt-2">
            <Button variant="outline" size="sm" onClick={() => void handleDiscard()} disabled={working}>
              放棄這次規劃
            </Button>
            <Button
              size="sm"
              onClick={() => void handleStart(chosenIds, excludedSections(draftChapters, chosen))}
              loading={working}
              disabled={!canGenerate || chosenIds.length === 0}
            >
              {!working && <FileText className="h-4 w-4" />}
              產生 {chosenIds.length} 個章節
            </Button>
          </div>
        </>
      )}

      {view === 'notes' && outline && (
        <>
          <div className="max-h-[60vh] overflow-auto rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark p-4">
            <div className="text-sm text-text dark:text-text-dark break-words">
              <h1 className="mt-2 mb-4 text-2xl font-bold">{outline.title}</h1>
              {outline.overview && <p className="my-2 leading-relaxed">{outline.overview}</p>}
            </div>
            {noteChapters.map((chapter) => (
              <ChapterNoteSection
                key={chapter.id}
                taskId={taskId}
                chapter={chapter}
                runtime={runtime[chapter.id]}
                canGenerate={canGenerate}
                onGenerate={enqueue}
              />
            ))}
          </div>

          <details className="rounded-lg border border-border dark:border-border-dark px-3 py-2">
            <summary className="cursor-pointer text-sm font-medium text-text dark:text-text-dark">
              參考資料
              <span className="ml-2 font-normal text-muted dark:text-muted-dark">修改後只會影響之後產生的章節</span>
            </summary>
            <div className="pt-3">
              <ReferenceInput
                taskId={taskId}
                references={references}
                text={refText}
                onTextChange={setRefText}
                onChange={setReferences}
              />
            </div>
          </details>

          <div className="flex flex-wrap items-center justify-between gap-2 pt-2">
            <p className="text-sm text-muted dark:text-muted-dark" aria-live="polite">
              已產生 {writtenCount} / {noteChapters.length} 章
              {busyCount > 0 && `，${busyCount} 章進行中`}
            </p>
            <div className="flex flex-wrap justify-end gap-2">
              {exportButtons}
              {busyCount > 0 ? (
                <Button variant="outline" size="sm" onClick={stopChapters}>
                  <Square className="h-4 w-4" />
                  停止
                </Button>
              ) : (
                <Button variant="outline" size="sm" onClick={() => setOverride('intro')}>
                  <ListChecks className="h-4 w-4" />
                  重新規劃
                </Button>
              )}
            </div>
          </div>
        </>
      )}

      {view === 'legacy' && notes && (
        <>
          <div className="max-h-[60vh] overflow-auto rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark p-4">
            <NoteRenderer markdown={notes.markdown} streaming={false} taskId={taskId} autoGenerateAnims={false} />
          </div>
          <div className="flex flex-wrap justify-end gap-2 pt-2">
            {exportButtons}
            <Button size="sm" onClick={() => setOverride('intro')} disabled={!canGenerate}>
              <FileText className="h-4 w-4" />
              重新產生
            </Button>
          </div>
        </>
      )}
    </div>
  )
}
