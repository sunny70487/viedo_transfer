import { useState, useEffect, useRef, useCallback } from 'react'
import { Settings, FileText, Copy, Check, Download, Square } from 'lucide-react'
import { Dialog } from '@/components/ui/Dialog'
import { Button } from '@/components/ui/Button'
import { api } from '@/api/client'
import { toast } from '@/stores/toast-store'
import { loadLlmSettings, saveLlmSettings } from '@/hooks/use-llm-settings'
import { NoteRenderer } from '@/components/editor/notes/NoteRenderer'

interface GenerateNotesDialogProps {
  open: boolean
  onClose: () => void
  taskId: string
  hasSubtitles: boolean
}

export function GenerateNotesDialog({
  open, onClose, taskId, hasSubtitles,
}: Readonly<GenerateNotesDialogProps>) {
  const [contentHint, setContentHint] = useState('')
  const [apiKeySet, setApiKeySet] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [markdown, setMarkdown] = useState('')
  const [justGenerated, setJustGenerated] = useState(false)
  const [copied, setCopied] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    if (!open) return
    const s = loadLlmSettings()
    setContentHint(s.content_hint)
    setApiKeySet(Boolean(s.api_key))
    setMarkdown('')
    setJustGenerated(false)
    let cancelled = false
    api.getStudyNotes(taskId)
      .then((md) => { if (!cancelled && md) setMarkdown(md) })
      .catch(() => { /* no saved note yet */ })
    return () => {
      cancelled = true
      abortRef.current?.abort()
    }
  }, [open, taskId])

  const handleGenerate = useCallback(async () => {
    const s = loadLlmSettings()
    if (!s.api_key) { toast('error', '請先在右上角 ⚙ 設定 LLM API Key'); return }
    if (!hasSubtitles) { toast('error', '目前沒有字幕資料'); return }

    saveLlmSettings({ content_hint: contentHint })
    setGenerating(true)
    setMarkdown('')
    setJustGenerated(false)
    const controller = new AbortController()
    abortRef.current = controller

    try {
      const stream = api.generateNotesStream(taskId, {
        api_key: s.api_key,
        base_url: s.base_url,
        model: s.model,
        content_hint: contentHint || undefined,
      }, controller.signal)
      for await (const event of stream) {
        if (event.type === 'delta' && event.text) {
          setMarkdown((prev) => prev + event.text)
        } else if (event.type === 'done') {
          setJustGenerated(true)
        } else if (event.type === 'error') {
          toast('error', `筆記生成失敗: ${event.message}`)
        }
      }
    } catch (e) {
      if ((e as Error).name !== 'AbortError') {
        toast('error', `筆記生成失敗: ${(e as Error).message}`)
      }
    } finally {
      abortRef.current = null
      setGenerating(false)
    }
  }, [taskId, contentHint, hasSubtitles])

  const handleCopy = useCallback(async () => {
    if (!markdown) return
    await navigator.clipboard.writeText(markdown)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }, [markdown])

  const handleDownload = useCallback(() => {
    if (!markdown) return
    const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `notes_${taskId}.md`
    a.click()
    URL.revokeObjectURL(url)
  }, [markdown, taskId])

  const canGenerate = apiKeySet && hasSubtitles && !generating

  return (
    <Dialog open={open} onClose={onClose} title="產生筆記" className="max-w-3xl">
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

        {!markdown && !generating && (
          <>
            <p className="text-sm text-muted dark:text-muted-dark">
              依字幕逐字稿整理成一份圖文並茂的繁體中文教學筆記（比喻、表格、Mermaid/ASCII 圖、應用場景與小結），並為重點概念繪製 SVG 動畫。
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
          </>
        )}

        {(markdown || generating) && (
          <div className="max-h-[60vh] overflow-auto rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark p-4">
            <NoteRenderer
              markdown={markdown}
              streaming={generating}
              taskId={taskId}
              autoGenerateAnims={justGenerated}
            />
            {generating && <span className="inline-block w-2 h-4 bg-primary/70 animate-pulse align-middle ml-0.5" />}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          {markdown && !generating && (
            <>
              <Button variant="outline" size="sm" onClick={handleCopy}>
                {copied ? <Check className="h-4 w-4 text-green-500" /> : <Copy className="h-4 w-4" />}
                {copied ? '已複製' : '複製'}
              </Button>
              <Button variant="outline" size="sm" onClick={handleDownload}>
                <Download className="h-4 w-4" />
                下載 .md
              </Button>
            </>
          )}
          {generating ? (
            <Button variant="outline" size="sm" onClick={() => abortRef.current?.abort()}>
              <Square className="h-4 w-4" />
              停止
            </Button>
          ) : (
            <Button size="sm" onClick={handleGenerate} disabled={!canGenerate}>
              <FileText className="h-4 w-4" />
              {markdown ? '重新產生' : '開始產生'}
            </Button>
          )}
        </div>
      </div>
    </Dialog>
  )
}
