import { Select } from '@/components/ui/Select'
import { Input } from '@/components/ui/Input'
import { MODEL_OPTIONS, LANGUAGE_OPTIONS } from '@/lib/constants'
import { ChevronDown, CheckCircle2, XCircle, Loader2 } from 'lucide-react'
import { useState, useEffect, useRef, useCallback } from 'react'
import { api } from '@/api/client'
import type { LlmModel } from '@/types/api'

const LLM_STORAGE_KEY = 'whisper_llm_settings'

interface LlmSettings {
  llm_enhance: string
  llm_api_key: string
  llm_base_url: string
  llm_model: string
  llm_content_hint: string
}

function loadLlmSettings(): LlmSettings {
  try {
    const raw = localStorage.getItem(LLM_STORAGE_KEY)
    if (raw) return JSON.parse(raw) as LlmSettings
  } catch { /* ignore */ }
  return {
    llm_enhance: 'false',
    llm_api_key: '',
    llm_base_url: 'https://api.openai.com/v1',
    llm_model: 'gpt-4o-mini',
    llm_content_hint: '',
  }
}

function saveLlmSettings(s: LlmSettings) {
  try {
    localStorage.setItem(LLM_STORAGE_KEY, JSON.stringify(s))
  } catch { /* ignore */ }
}

interface TranscriptionOptionsProps {
  values: Record<string, string>
  onChange: (key: string, value: string) => void
}

function Section({ title, children, defaultOpen = false }: Readonly<{ title: string; children: React.ReactNode; defaultOpen?: boolean }>) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="border border-border dark:border-border-dark rounded-lg overflow-hidden">
      <button
        type="button"
        className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-text dark:text-text-dark hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors cursor-pointer"
        onClick={() => setOpen(!open)}
      >
        {title}
        <ChevronDown className={`h-4 w-4 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && <div className="px-4 pb-4 space-y-3 border-t border-border dark:border-border-dark">{children}</div>}
    </div>
  )
}

type ModelStatus = 'idle' | 'loading' | 'success' | 'error'

export function TranscriptionOptions({ values, onChange }: Readonly<TranscriptionOptionsProps>) {
  const [llm, setLlm] = useState<LlmSettings>(() => {
    const saved = loadLlmSettings()
    for (const [k, v] of Object.entries(saved)) {
      if (values[k] === undefined) onChange(k, v)
    }
    return saved
  })

  const [models, setModels] = useState<LlmModel[]>([])
  const [modelStatus, setModelStatus] = useState<ModelStatus>('idle')
  const [modelError, setModelError] = useState('')
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const updateLlm = useCallback((key: keyof LlmSettings, value: string) => {
    setLlm((prev) => {
      const next = { ...prev, [key]: value }
      saveLlmSettings(next)
      return next
    })
    onChange(key, value)
  }, [onChange])

  const fetchModels = useCallback(async (key: string, url: string) => {
    if (!key || !url) {
      setModels([])
      setModelStatus('idle')
      return
    }
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
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (!llm.llm_api_key || !llm.llm_base_url) {
      setModels([])
      setModelStatus('idle')
      return
    }
    debounceRef.current = setTimeout(() => {
      fetchModels(llm.llm_api_key, llm.llm_base_url)
    }, 800)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [llm.llm_api_key, llm.llm_base_url, fetchModels])

  const llmEnabled = llm.llm_enhance === 'true'

  return (
    <div className="space-y-3 mt-4">
      <Section title="模型設定" defaultOpen>
        <label className="block text-sm font-medium text-text dark:text-text-dark mt-3">ASR 模型</label>
        <Select
          options={MODEL_OPTIONS as unknown as { value: string; label: string; group?: string }[]}
          value={values.model_size || 'qwen3-asr-1.7b'}
          onChange={(e) => onChange('model_size', e.target.value)}
        />
        <label className="block text-sm font-medium text-text dark:text-text-dark">語言</label>
        <Select
          options={LANGUAGE_OPTIONS as unknown as { value: string; label: string }[]}
          value={values.language || ''}
          onChange={(e) => onChange('language', e.target.value)}
        />
      </Section>

      <Section title="AI 字幕增強">
        <div className="flex items-center gap-2 mt-3">
          <input
            type="checkbox"
            id="llm-enhance"
            className="rounded cursor-pointer"
            checked={llmEnabled}
            onChange={(e) => updateLlm('llm_enhance', String(e.target.checked))}
          />
          <label htmlFor="llm-enhance" className="text-sm text-text dark:text-text-dark cursor-pointer">
            啟用 LLM 字幕校正
          </label>
        </div>
        {llmEnabled && (
          <p className="text-xs text-muted dark:text-muted-dark -mt-1">
            轉錄完成後使用大型語言模型修正音譯錯誤、還原英文術語、改善標點
          </p>
        )}
        {llmEnabled && (
          <div className="space-y-3">
            <div>
              <label className="block text-sm font-medium text-text dark:text-text-dark">Base URL</label>
              <Input
                type="text"
                placeholder="https://api.openai.com/v1"
                value={llm.llm_base_url}
                onChange={(e) => updateLlm('llm_base_url', e.target.value)}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-text dark:text-text-dark">API Key</label>
              <Input
                type="password"
                placeholder="sk-..."
                autoComplete="off"
                value={llm.llm_api_key}
                onChange={(e) => updateLlm('llm_api_key', e.target.value)}
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
                  value={llm.llm_model}
                  onChange={(e) => updateLlm('llm_model', e.target.value)}
                >
                  {models.map((m) => (
                    <option key={m.id} value={m.id}>{m.name}</option>
                  ))}
                </select>
              ) : (
                <Input
                  type="text"
                  placeholder="gpt-4o-mini"
                  value={llm.llm_model}
                  onChange={(e) => updateLlm('llm_model', e.target.value)}
                />
              )}
            </div>
            <div>
              <label className="block text-sm font-medium text-text dark:text-text-dark">內容描述 (選填)</label>
              <textarea
                className="w-full rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark px-3 py-2 text-sm text-text dark:text-text-dark placeholder:text-muted/60 focus:outline-none focus:ring-2 focus:ring-primary/40 resize-y min-h-[40px]"
                rows={2}
                placeholder="例如：資訊安全課程，涉及 IDA、PE、Assembly 等專業術語"
                value={llm.llm_content_hint}
                onChange={(e) => updateLlm('llm_content_hint', e.target.value)}
              />
            </div>
          </div>
        )}
      </Section>

      <Section title="進階選項">
        <div className="flex items-center gap-2 mt-3">
          <input type="checkbox" id="vad" className="rounded cursor-pointer"
            checked={values.vad_filter !== 'false'}
            onChange={(e) => onChange('vad_filter', String(e.target.checked))} />
          <label htmlFor="vad" className="text-sm text-text dark:text-text-dark cursor-pointer">語音活動檢測 (VAD)</label>
        </div>
        <div className="flex items-center gap-2">
          <input type="checkbox" id="wordts" className="rounded cursor-pointer"
            checked={values.word_timestamps !== 'false'}
            onChange={(e) => onChange('word_timestamps', String(e.target.checked))} />
          <label htmlFor="wordts" className="text-sm text-text dark:text-text-dark cursor-pointer">詞級時間戳</label>
        </div>
        <div className="flex items-center gap-2">
          <input type="checkbox" id="diarize" className="rounded cursor-pointer"
            checked={values.speaker_diarization === 'true'}
            onChange={(e) => onChange('speaker_diarization', String(e.target.checked))} />
          <label htmlFor="diarize" className="text-sm text-text dark:text-text-dark cursor-pointer">說話者辨識</label>
        </div>
        {values.speaker_diarization === 'true' && (
          <div>
            <label className="text-sm text-muted dark:text-muted-dark">說話者人數 (選填)</label>
            <Input type="number" min={1} max={20} placeholder="自動偵測"
              value={values.num_speakers || ''}
              onChange={(e) => onChange('num_speakers', e.target.value)} />
          </div>
        )}
      </Section>

      <Section title="分割選項">
        <div className="flex items-center gap-2 mt-3">
          <input type="checkbox" id="split" className="rounded cursor-pointer"
            checked={values.split_segments !== 'false'}
            onChange={(e) => onChange('split_segments', String(e.target.checked))} />
          <label htmlFor="split" className="text-sm text-text dark:text-text-dark cursor-pointer">分割音檔處理</label>
        </div>
        {values.split_segments !== 'false' && (
          <div>
            <label className="text-sm text-muted dark:text-muted-dark">片段時長 (秒)</label>
            <Input type="number" min={10} max={300}
              value={values.segment_duration || '60'}
              onChange={(e) => onChange('segment_duration', e.target.value)} />
          </div>
        )}
      </Section>
    </div>
  )
}
