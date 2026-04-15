import { useState, useEffect, useCallback } from 'react'
import { Settings, Sparkles, Languages, BookOpen, Copy, Check } from 'lucide-react'
import { Dialog } from '@/components/ui/Dialog'
import { Button } from '@/components/ui/Button'
import { api } from '@/api/client'
import { toast } from '@/stores/toast-store'
import { loadLlmSettings, saveLlmSettings } from '@/hooks/use-llm-settings'
import type { Subtitle, SubtitleNotes } from '@/types/api'

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

type DialogMode = 'enhance' | 'translate' | 'summarize'

interface LlmEnhanceDialogProps {
  open: boolean
  onClose: () => void
  subtitles: Subtitle[]
  taskId: string
  onEnhanced: (subs: Subtitle[]) => void
  onSeekTo?: (time: number) => void
}

export function LlmEnhanceDialog({
  open, onClose, subtitles, taskId, onEnhanced, onSeekTo,
}: Readonly<LlmEnhanceDialogProps>) {
  const [mode, setMode] = useState<DialogMode>('enhance')
  const [contentHint, setContentHint] = useState('')
  const [apiKeySet, setApiKeySet] = useState(false)

  // enhance / translate state
  const [enhancing, setEnhancing] = useState(false)
  const [progress, setProgress] = useState({ batch: 0, total: 0, percent: 0 })
  const [infoMsg, setInfoMsg] = useState('')
  const [targetLang, setTargetLang] = useState('英文')
  const [bilingual, setBilingual] = useState(false)

  // summarize state
  const [notes, setNotes] = useState<SubtitleNotes | null>(null)
  const [summarizing, setSummarizing] = useState(false)
  const [summaryError, setSummaryError] = useState('')
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!open) return
    const s = loadLlmSettings()
    setContentHint(s.content_hint)
    setApiKeySet(Boolean(s.api_key))
  }, [open])

  useEffect(() => {
    if (!open || mode !== 'summarize') return
    api.getSubtitleNotes(taskId)
      .then((n) => { if (n) setNotes(n) })
      .catch(() => {})
  }, [open, mode, taskId])

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
        subtitles: subtitles.map((sub) => ({
          index: sub.index,
          start_time: sub.start_time,
          end_time: sub.end_time,
          text: sub.text,
        })),
        api_key: s.api_key,
        base_url: s.base_url,
        model: s.model,
        content_hint: contentHint || undefined,
        merge_short: mode === 'enhance',
        mode: mode as 'enhance' | 'translate',
        target_language: mode === 'translate' ? targetLang : undefined,
        bilingual: mode === 'translate' ? bilingual : undefined,
      })

      for await (const event of stream) {
        if (event.type === 'progress') {
          setProgress({
            batch: event.batch ?? 0,
            total: event.total ?? 0,
            percent: event.percent ?? 0,
          })
        } else if (event.type === 'info' && event.message) {
          setInfoMsg(event.message)
        } else if (event.type === 'result' && event.subtitles) {
          const enhanced: Subtitle[] = event.subtitles.map((sub) => ({
            index: sub.index,
            start_time: sub.start_time,
            end_time: sub.end_time,
            text: sub.text,
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

  const handleSummarize = useCallback(async () => {
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
  }, [taskId])

  const handleCopySummary = useCallback(async () => {
    if (!notes?.summary) return
    await navigator.clipboard.writeText(notes.summary)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }, [notes?.summary])

  const canEnhance = apiKeySet && subtitles.length > 0
  const dialogTitle = mode === 'summarize'
    ? 'AI 摘要'
    : mode === 'translate' ? 'AI 字幕翻譯' : 'AI 字幕增強'

  return (
    <Dialog open={open} onClose={onClose} title={dialogTitle}>
      <div className="space-y-4">
        {!enhancing && (
          <div className="flex rounded-lg border border-border dark:border-border-dark overflow-hidden" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'enhance'}
              className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-sm font-medium transition-colors cursor-pointer ${
                mode === 'enhance'
                  ? 'bg-primary text-white'
                  : 'text-text dark:text-text-dark hover:bg-gray-50 dark:hover:bg-gray-800'
              }`}
              onClick={() => setMode('enhance')}
            >
              <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
              校對增強
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'translate'}
              className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-sm font-medium transition-colors cursor-pointer ${
                mode === 'translate'
                  ? 'bg-primary text-white'
                  : 'text-text dark:text-text-dark hover:bg-gray-50 dark:hover:bg-gray-800'
              }`}
              onClick={() => setMode('translate')}
            >
              <Languages className="h-3.5 w-3.5" aria-hidden="true" />
              翻譯字幕
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'summarize'}
              aria-label="生成摘要"
              className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-sm font-medium transition-colors cursor-pointer ${
                mode === 'summarize'
                  ? 'bg-primary text-white'
                  : 'text-text dark:text-text-dark hover:bg-gray-50 dark:hover:bg-gray-800'
              }`}
              onClick={() => setMode('summarize')}
            >
              <BookOpen className="h-3.5 w-3.5" aria-hidden="true" />
              摘要
            </button>
          </div>
        )}

        {mode !== 'summarize' && (
          <p className="text-sm text-muted dark:text-muted-dark">
            {mode === 'translate'
              ? `將 ${subtitles.length} 行字幕翻譯為其他語言。`
              : `修正音譯錯誤、還原英文術語、改善標點，並自動合併過短的斷句。共 ${subtitles.length} 行字幕。`
            }
          </p>
        )}

        {/* ── enhance / translate progress ── */}
        {enhancing && (
          <div className="space-y-2">
            {infoMsg && (
              <p className="text-xs text-blue-500 dark:text-blue-400" aria-live="polite">{infoMsg}</p>
            )}
            <div className="flex items-center justify-between text-sm">
              <span className="text-text dark:text-text-dark">
                正在處理第 {progress.batch}/{progress.total} 批
              </span>
              <span className="text-muted dark:text-muted-dark font-mono" aria-live="polite">
                {progress.percent}%
              </span>
            </div>
            <div
              className="h-2.5 w-full rounded-full bg-gray-200 dark:bg-gray-700 overflow-hidden"
              role="progressbar"
              aria-valuenow={progress.percent}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div
                className="h-full rounded-full bg-primary transition-all duration-500 ease-out"
                style={{ width: `${progress.percent}%` }}
              />
            </div>
          </div>
        )}

        {/* ── enhance / translate fields ── */}
        {!enhancing && mode !== 'summarize' && (
          <>
            {!apiKeySet && (
              <div
                role="alert"
                className="flex items-center gap-2 rounded-lg border border-amber-300 dark:border-amber-600 bg-amber-50 dark:bg-amber-900/20 px-3 py-2 text-sm text-amber-700 dark:text-amber-400"
              >
                <Settings className="h-4 w-4 shrink-0" aria-hidden="true" />
                請先點選右上角 ⚙️ 設定 LLM API Key
              </div>
            )}

            {mode === 'translate' && (
              <>
                <div>
                  <label htmlFor="target-lang" className="block text-sm font-medium text-text dark:text-text-dark mb-1">
                    目標語言
                  </label>
                  <select
                    id="target-lang"
                    className="h-10 w-full rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark px-3 text-sm text-text dark:text-text-dark focus:outline-none focus:ring-2 focus:ring-primary/50 cursor-pointer"
                    value={targetLang}
                    onChange={(e) => setTargetLang(e.target.value)}
                  >
                    {TARGET_LANGUAGES.map((lang) => (
                      <option key={lang.value} value={lang.value}>{lang.label}</option>
                    ))}
                  </select>
                </div>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={bilingual}
                    onChange={(e) => setBilingual(e.target.checked)}
                    className="rounded border-border accent-primary"
                  />
                  <span className="text-sm text-text dark:text-text-dark">雙語字幕（原文 + 譯文）</span>
                </label>
              </>
            )}

            <div>
              <label htmlFor="content-hint" className="block text-sm font-medium text-text dark:text-text-dark mb-1">
                內容描述 <span className="text-muted dark:text-muted-dark font-normal">（選填）</span>
              </label>
              <textarea
                id="content-hint"
                className="w-full rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark px-3 py-2 text-sm text-text dark:text-text-dark placeholder:text-muted/60 focus:outline-none focus:ring-2 focus:ring-primary/40 resize-y min-h-[40px]"
                rows={2}
                placeholder="例如：資訊安全課程，涉及 IDA、PE、Assembly 等專業術語"
                value={contentHint}
                onChange={(e) => setContentHint(e.target.value)}
              />
            </div>
          </>
        )}

        {/* ── summarize skeleton (loading) ── */}
        {mode === 'summarize' && summarizing && (
          <div className="space-y-3" aria-live="polite" aria-busy="true">
            <div className="rounded-lg border border-border dark:border-border-dark p-3 space-y-2">
              <div className="h-3 w-full rounded bg-gray-200 dark:bg-gray-700 animate-pulse" />
              <div className="h-3 w-4/5 rounded bg-gray-200 dark:bg-gray-700 animate-pulse" />
              <div className="h-3 w-3/5 rounded bg-gray-200 dark:bg-gray-700 animate-pulse" />
            </div>
            <div className="space-y-1.5">
              {[1, 2, 3].map((n) => (
                <div key={n} className="flex items-center gap-2 px-2 py-2.5">
                  <div className="h-3 w-10 rounded bg-gray-200 dark:bg-gray-700 animate-pulse shrink-0" />
                  <div className="h-3 flex-1 rounded bg-gray-200 dark:bg-gray-700 animate-pulse" />
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── summarize results / generate ── */}
        {mode === 'summarize' && !summarizing && (
          <div className="space-y-3">
            {summaryError && (
              <p className="text-sm text-danger" role="alert">{summaryError}</p>
            )}
            {!apiKeySet && (
              <div
                role="alert"
                className="flex items-center gap-2 rounded-lg border border-amber-300 dark:border-amber-600 bg-amber-50 dark:bg-amber-900/20 px-3 py-2 text-sm text-amber-700 dark:text-amber-400"
              >
                <Settings className="h-4 w-4 shrink-0" aria-hidden="true" />
                請先點選右上角 ⚙️ 設定 LLM API Key
              </div>
            )}
            {notes ? (
              <>
                <div className="relative rounded-lg border border-border dark:border-border-dark bg-bg dark:bg-bg-dark p-3">
                  <p className="text-sm text-text dark:text-text-dark leading-relaxed pr-8">
                    {notes.summary}
                  </p>
                  <button
                    type="button"
                    onClick={handleCopySummary}
                    aria-label="複製摘要"
                    className="absolute top-2 right-2 p-1.5 rounded text-muted hover:text-text dark:hover:text-text-dark transition-colors"
                  >
                    {copied
                      ? <Check className="h-3.5 w-3.5 text-green-500" aria-hidden="true" />
                      : <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                    }
                  </button>
                </div>
                {notes.chapters.length > 0 && (
                  <div className="space-y-0.5">
                    <p className="text-xs font-medium text-muted dark:text-muted-dark uppercase tracking-wider px-2 pb-1">
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
                          onClick={() => onSeekTo?.(ch.time)}
                          aria-label={`跳至 ${ts} — ${ch.title}`}
                          className="flex items-center gap-2 w-full text-left px-2 py-2.5 min-h-[44px] rounded hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors group"
                        >
                          <span className="font-mono text-xs text-primary shrink-0 tabular-nums">{ts}</span>
                          <span className="text-sm text-text dark:text-text-dark group-hover:text-primary transition-colors">{ch.title}</span>
                        </button>
                      )
                    })}
                  </div>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleSummarize}
                  disabled={!apiKeySet}
                  className="w-full"
                >
                  重新生成
                </Button>
              </>
            ) : (
              <Button
                size="sm"
                onClick={handleSummarize}
                disabled={!apiKeySet}
                className="w-full"
              >
                <BookOpen className="h-4 w-4" aria-hidden="true" />
                開始生成摘要
              </Button>
            )}
          </div>
        )}

        {/* ── action row ── */}
        {mode !== 'summarize' && (
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" size="sm" onClick={onClose} disabled={enhancing}>
              取消
            </Button>
            <Button size="sm" onClick={handleEnhance} disabled={!canEnhance || enhancing} loading={enhancing}>
              {mode === 'translate'
                ? <Languages className="h-4 w-4" aria-hidden="true" />
                : <Sparkles className="h-4 w-4" aria-hidden="true" />
              }
              {enhancing
                ? `${mode === 'translate' ? '翻譯' : '增強'}中 (${progress.batch}/${progress.total})`
                : mode === 'translate' ? '開始翻譯' : '開始增強'
              }
            </Button>
          </div>
        )}
        {mode === 'summarize' && !summarizing && (
          <div className="flex justify-end pt-2">
            <Button variant="outline" size="sm" onClick={onClose}>關閉</Button>
          </div>
        )}
      </div>
    </Dialog>
  )
}
