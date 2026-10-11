import { useCallback, useEffect, useMemo, useState } from 'react'
import { RefreshCw, Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { api } from '@/api/client'
import { loadLlmSettings } from '@/hooks/use-llm-settings'
import type { ConceptAnimSpec } from '@/types/api'
import { runInAnimQueue } from './concept-anim-queue'

type Status = 'loading' | 'empty' | 'generating' | 'ready' | 'error'

interface ConceptAnimationCardProps {
  taskId: string
  spec: ConceptAnimSpec
  autoGenerate: boolean
}

export function ConceptAnimationCard({ taskId, spec, autoGenerate }: Readonly<ConceptAnimationCardProps>) {
  const [svg, setSvg] = useState<string | null>(null)
  const [status, setStatus] = useState<Status>('loading')
  const [error, setError] = useState('')

  const generate = useCallback(async () => {
    const s = loadLlmSettings()
    if (!s.api_key) {
      setError('請先在右上角 ⚙ 設定 LLM API Key')
      setStatus('error')
      return
    }
    setStatus('generating')
    setError('')
    try {
      const result = await runInAnimQueue(() => api.generateConceptAnimation(taskId, spec.id, {
        title: spec.title,
        brief: spec.brief,
        api_key: s.api_key,
        base_url: s.base_url,
        model: s.svg_model || s.model,
        content_hint: s.content_hint || undefined,
      }))
      setSvg(result)
      setStatus('ready')
    } catch (e) {
      setError((e as Error).message)
      setStatus('error')
    }
  }, [taskId, spec.id, spec.title, spec.brief])

  const [initialAutoGenerate] = useState(autoGenerate)

  useEffect(() => {
    let cancelled = false
    api.getConceptAnimation(taskId, spec.id)
      .then((saved) => {
        if (cancelled) return
        if (saved) {
          setSvg(saved)
          setStatus('ready')
        } else if (initialAutoGenerate) {
          void generate()
        } else {
          setStatus('empty')
        }
      })
      .catch(() => { if (!cancelled) setStatus('empty') })
    return () => { cancelled = true }
  }, [taskId, spec.id, initialAutoGenerate, generate])

  const src = useMemo(
    () => (svg ? URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' })) : null),
    [svg],
  )
  useEffect(() => () => { if (src) URL.revokeObjectURL(src) }, [src])

  return (
    <figure className="my-4 overflow-hidden rounded-xl border border-border dark:border-border-dark bg-surface dark:bg-surface-dark">
      <div className="flex items-center justify-between gap-2 border-b border-border dark:border-border-dark px-3 py-2">
        <figcaption className="flex items-center gap-1.5 text-sm font-medium">
          <Sparkles className="h-4 w-4 text-primary" aria-hidden="true" />
          {spec.title}
        </figcaption>
        {status === 'ready' && (
          <Button variant="ghost" size="sm" onClick={() => void generate()} aria-label={`重畫 ${spec.title} 動畫`}>
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            重畫
          </Button>
        )}
      </div>

      <div className="aspect-video w-full bg-bg dark:bg-bg-dark">
        {status === 'ready' && src && (
          <img src={src} alt={`${spec.title}：${spec.brief}`} className="h-full w-full object-contain" />
        )}
        {(status === 'loading' || status === 'generating') && (
          <div className="flex h-full flex-col items-center justify-center gap-2 animate-pulse text-xs text-muted dark:text-muted-dark" aria-busy="true">
            {status === 'generating' ? '動畫繪製中…' : '載入中…'}
          </div>
        )}
        {status === 'empty' && (
          <div className="flex h-full flex-col items-center justify-center gap-2 p-4 text-center">
            <p className="text-xs text-muted dark:text-muted-dark">{spec.brief}</p>
            <Button size="sm" onClick={() => void generate()}>
              <Sparkles className="h-4 w-4" aria-hidden="true" />
              生成動畫
            </Button>
          </div>
        )}
        {status === 'error' && (
          <div className="flex h-full flex-col items-center justify-center gap-2 p-4 text-center" role="alert">
            <p className="text-sm text-danger">{error || '動畫生成失敗'}</p>
            <Button variant="outline" size="sm" onClick={() => void generate()}>重試</Button>
          </div>
        )}
      </div>
    </figure>
  )
}
