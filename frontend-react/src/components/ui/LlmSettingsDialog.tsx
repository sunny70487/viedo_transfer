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
          <label htmlFor="llm-base-url" className="block text-sm font-medium text-text dark:text-text-dark mb-1">
            Base URL
          </label>
          <Input
            id="llm-base-url"
            type="text"
            placeholder="https://api.openai.com/v1"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
          />
        </div>

        <div>
          <label htmlFor="llm-api-key" className="block text-sm font-medium text-text dark:text-text-dark mb-1">
            API Key
          </label>
          <Input
            id="llm-api-key"
            type="password"
            placeholder="sk-..."
            autoComplete="off"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
          />
        </div>

        <div>
          <div className="flex items-center gap-2 mb-1">
            <label htmlFor="llm-model" className="block text-sm font-medium text-text dark:text-text-dark">
              模型
            </label>
            {modelStatus === 'loading' && (
              <Loader2 className="h-3.5 w-3.5 animate-spin text-muted" aria-label="載入模型列表" />
            )}
            {modelStatus === 'success' && (
              <CheckCircle2 className="h-3.5 w-3.5 text-green-500" aria-label="連線成功" />
            )}
            {modelStatus === 'error' && (
              <span className="flex items-center gap-1 text-xs text-danger" role="alert">
                <XCircle className="h-3.5 w-3.5" aria-hidden="true" />
                {modelError || '連線失敗'}
              </span>
            )}
          </div>
          {models.length > 0 ? (
            <select
              id="llm-model"
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
              id="llm-model"
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
