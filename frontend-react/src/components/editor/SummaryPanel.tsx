import { useState, useEffect, useCallback } from 'react'
import { BookOpen, Copy, Check, Settings } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { api } from '@/api/client'
import { loadLlmSettings } from '@/hooks/use-llm-settings'
import type { SubtitleNotes } from '@/types/api'

interface SummaryPanelProps {
  taskId: string
  onSeekTo: (time: number) => void
  disabled?: boolean
}

export function SummaryPanel({ taskId, onSeekTo, disabled }: Readonly<SummaryPanelProps>) {
  const [notes, setNotes] = useState<SubtitleNotes | null>(null)
  const [summarizing, setSummarizing] = useState(false)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)
  const [apiKeySet, setApiKeySet] = useState(false)

  useEffect(() => {
    setApiKeySet(Boolean(loadLlmSettings().api_key))
  }, [])

  useEffect(() => {
    api.getSubtitleNotes(taskId)
      .then((n) => { if (n) setNotes(n) })
      .catch(() => {})
  }, [taskId])

  const handleGenerate = useCallback(async () => {
    const s = loadLlmSettings()
    if (!s.api_key) { setError('請先在右上角 ⚙ 設定 LLM API Key'); return }
    setSummarizing(true)
    setError('')
    try {
      const result = await api.summarizeSubtitles(taskId, {
        api_key: s.api_key,
        base_url: s.base_url,
        model: s.model,
        content_hint: s.content_hint || undefined,
      })
      setNotes(result)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSummarizing(false)
    }
  }, [taskId])

  const handleCopy = useCallback(async () => {
    if (!notes?.summary) return
    await navigator.clipboard.writeText(notes.summary)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }, [notes?.summary])

  return (
    <section aria-label="AI 摘要" className="rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BookOpen className="h-4 w-4 text-muted dark:text-muted-dark" aria-hidden="true" />
          <h2 className="text-sm font-semibold text-text dark:text-text-dark">AI 摘要</h2>
        </div>
        {notes && !summarizing && (
          <Button
            variant="ghost"
            size="sm"
            onClick={handleGenerate}
            disabled={disabled || !apiKeySet || summarizing}
            aria-label="重新生成摘要"
          >
            重新生成
          </Button>
        )}
      </div>

      {!apiKeySet && (
        <div
          role="alert"
          className="flex items-center gap-2 rounded-lg border border-amber-300 dark:border-amber-600 bg-amber-50 dark:bg-amber-900/20 px-3 py-2 text-sm text-amber-700 dark:text-amber-400"
        >
          <Settings className="h-4 w-4 shrink-0" aria-hidden="true" />
          請先點選右上角 ⚙ 設定 LLM API Key
        </div>
      )}

      {error && (
        <p className="text-sm text-danger" role="alert">{error}</p>
      )}

      {/* skeleton while generating */}
      {summarizing && (
        <div className="space-y-3" aria-live="polite" aria-busy="true">
          <div className="space-y-2">
            <div className="h-3 w-full rounded bg-gray-200 dark:bg-gray-700 animate-pulse" />
            <div className="h-3 w-4/5 rounded bg-gray-200 dark:bg-gray-700 animate-pulse" />
            <div className="h-3 w-3/5 rounded bg-gray-200 dark:bg-gray-700 animate-pulse" />
          </div>
          <div className="space-y-1.5">
            {[1, 2, 3].map((n) => (
              <div key={n} className="flex items-center gap-2 py-2">
                <div className="h-3 w-10 rounded bg-gray-200 dark:bg-gray-700 animate-pulse shrink-0" />
                <div className="h-3 flex-1 rounded bg-gray-200 dark:bg-gray-700 animate-pulse" />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* summary content */}
      {!summarizing && notes && (
        <div className="space-y-3">
          <div className="relative rounded-lg border border-border dark:border-border-dark bg-bg dark:bg-bg-dark p-3">
            <p className="text-sm text-text dark:text-text-dark leading-relaxed pr-8">
              {notes.summary}
            </p>
            <button
              type="button"
              onClick={handleCopy}
              aria-label="複製摘要"
              className="absolute top-2 right-2 p-1.5 rounded text-muted hover:text-text dark:hover:text-text-dark transition-colors"
            >
              {copied
                ? <Check className="h-3.5 w-3.5 text-green-500" aria-hidden="true" />
                : <Copy className="h-3.5 w-3.5" aria-hidden="true" />}
            </button>
          </div>

          {notes.chapters.length > 0 && (
            <div className="space-y-0.5">
              <p className="text-xs font-medium text-muted dark:text-muted-dark uppercase tracking-wider px-1 pb-1">
                章節
              </p>
              {notes.chapters.map((ch, i) => {
                const m = Math.floor(ch.time / 60)
                const s = Math.floor(ch.time % 60)
                const ts = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
                return (
                  <button
                    key={i}
                    type="button"
                    onClick={() => onSeekTo(ch.time)}
                    aria-label={`跳至 ${ts} — ${ch.title}`}
                    className="flex items-center gap-3 w-full text-left px-1 py-2 min-h-[44px] rounded hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors group"
                  >
                    <span className="font-mono text-xs text-primary shrink-0 tabular-nums">{ts}</span>
                    <span className="text-sm text-text dark:text-text-dark group-hover:text-primary transition-colors">{ch.title}</span>
                  </button>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* initial generate button */}
      {!summarizing && !notes && (
        <Button
          size="sm"
          onClick={handleGenerate}
          disabled={disabled || !apiKeySet}
          loading={summarizing}
          className="w-full"
        >
          <BookOpen className="h-4 w-4" aria-hidden="true" />
          生成 AI 摘要
        </Button>
      )}
    </section>
  )
}
