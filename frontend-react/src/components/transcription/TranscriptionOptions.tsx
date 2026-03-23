import { Select } from '@/components/ui/Select'
import { Input } from '@/components/ui/Input'
import { MODEL_OPTIONS, LANGUAGE_OPTIONS } from '@/lib/constants'
import { ChevronDown } from 'lucide-react'
import { useState } from 'react'

interface TranscriptionOptionsProps {
  values: Record<string, string>
  onChange: (key: string, value: string) => void
}

function Section({ title, children, defaultOpen = false }: { title: string; children: React.ReactNode; defaultOpen?: boolean }) {
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

export function TranscriptionOptions({ values, onChange }: TranscriptionOptionsProps) {
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
