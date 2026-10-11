import { useState, useEffect, useCallback } from 'react'
import { Network, Maximize2, Settings } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { api } from '@/api/client'
import { loadLlmSettings } from '@/hooks/use-llm-settings'
import type { Mindmap } from '@/types/api'
import { MindmapView } from './MindmapView'

interface MindmapPanelProps {
  taskId: string
  onSeekTo: (time: number) => void
  disabled?: boolean
}

export function MindmapPanel({ taskId, onSeekTo, disabled }: Readonly<MindmapPanelProps>) {
  const [mindmap, setMindmap] = useState<Mindmap | null>(null)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState('')
  const [apiKeySet, setApiKeySet] = useState(false)
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    setApiKeySet(Boolean(loadLlmSettings().api_key))
  }, [])

  useEffect(() => {
    let cancelled = false
    api.getMindmap(taskId)
      .then((m) => { if (!cancelled && m) setMindmap(m) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [taskId])

  const handleGenerate = useCallback(async () => {
    const s = loadLlmSettings()
    if (!s.api_key) { setError('請先在右上角 ⚙ 設定 LLM API Key'); return }
    setGenerating(true)
    setError('')
    try {
      const result = await api.generateMindmap(taskId, {
        api_key: s.api_key,
        base_url: s.base_url,
        model: s.model,
        content_hint: s.content_hint || undefined,
      })
      setMindmap(result)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setGenerating(false)
    }
  }, [taskId])

  const seekAndClose = useCallback((t: number) => {
    setExpanded(false)
    onSeekTo(t)
  }, [onSeekTo])

  return (
    <section aria-label="心智圖" className="rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Network className="h-4 w-4 text-muted dark:text-muted-dark" aria-hidden="true" />
          <h2 className="text-sm font-semibold text-text dark:text-text-dark">心智圖</h2>
        </div>
        {mindmap && !generating && (
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="sm" onClick={() => setExpanded(true)} aria-label="放大檢視心智圖">
              <Maximize2 className="h-4 w-4" aria-hidden="true" />
            </Button>
            <Button variant="ghost" size="sm" onClick={handleGenerate} disabled={disabled || !apiKeySet} aria-label="重新生成心智圖">
              重新生成
            </Button>
          </div>
        )}
      </div>

      {!apiKeySet && (
        <div role="alert" className="flex items-center gap-2 rounded-lg border border-amber-300 dark:border-amber-600 bg-amber-50 dark:bg-amber-900/20 px-3 py-2 text-sm text-amber-700 dark:text-amber-400">
          <Settings className="h-4 w-4 shrink-0" aria-hidden="true" />
          請先點選右上角 ⚙ 設定 LLM API Key
        </div>
      )}

      {error && <p className="text-sm text-danger" role="alert">{error}</p>}

      {generating && (
        <div className="h-72 rounded-lg bg-gray-200 dark:bg-gray-700 animate-pulse" aria-live="polite" aria-busy="true" />
      )}

      {!generating && mindmap && !expanded && (
        <>
          <MindmapView root={mindmap.root} onSeekTo={onSeekTo} expandLevel={2} className="h-96" />
          <p className="text-xs text-muted dark:text-muted-dark">
            點節點跳至該時間；點圓點展開細節，或按右上角放大檢視全貌
          </p>
        </>
      )}

      {!generating && !mindmap && (
        <Button size="sm" onClick={handleGenerate} disabled={disabled || !apiKeySet} className="w-full">
          <Network className="h-4 w-4" aria-hidden="true" />
          生成心智圖
        </Button>
      )}

      {mindmap && (
        <Dialog open={expanded} onClose={() => setExpanded(false)} title="心智圖" className="max-w-[95vw]">
          {expanded && <MindmapView root={mindmap.root} onSeekTo={seekAndClose} className="h-[calc(90vh-7rem)]" />}
        </Dialog>
      )}
    </section>
  )
}
