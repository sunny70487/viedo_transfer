import { useState } from 'react'
import { Link2, Send } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { TranscriptionOptions } from './TranscriptionOptions'
import { useTranscribeUrl } from '@/hooks/use-tasks'

const FORMAT_OPTIONS = [
  { value: 'audio', label: '僅音檔' },
  { value: 'video', label: '影片' },
  { value: 'both', label: '兩者' },
]

export function URLForm() {
  const [url, setUrl] = useState('')
  const [downloadFormat, setDownloadFormat] = useState('audio')
  const [options, setOptions] = useState<Record<string, string>>({
    model_size: 'qwen3-asr-1.7b',
    vad_filter: 'true',
    word_timestamps: 'true',
    split_segments: 'true',
    segment_duration: '60',
  })
  const mutation = useTranscribeUrl()

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!url.trim()) return
    mutation.mutate({
      url: url.trim(),
      download_format: downloadFormat,
      ...Object.fromEntries(Object.entries(options).filter(([, v]) => v !== '')),
    })
    setUrl('')
  }

  const handleOptionChange = (key: string, value: string) => {
    setOptions((prev) => ({ ...prev, [key]: value }))
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label htmlFor="url-input" className="block text-sm font-medium text-text dark:text-text-dark mb-1.5">URL</label>
        <div className="relative">
          <Link2 className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted" />
          <Input
            id="url-input"
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="YouTube、Bilibili 或直接音檔/影片連結"
            className="pl-10"
            required
          />
        </div>
      </div>
      <div>
        <label className="block text-sm font-medium text-text dark:text-text-dark mb-1.5">下載格式</label>
        <Select options={FORMAT_OPTIONS} value={downloadFormat} onChange={(e) => setDownloadFormat(e.target.value)} />
      </div>
      <TranscriptionOptions values={options} onChange={handleOptionChange} />
      <Button type="submit" className="w-full" loading={mutation.isPending}>
        <Send className="h-4 w-4" />
        開始轉錄
      </Button>
      {mutation.isError && (
        <p className="text-sm text-danger">{(mutation.error as Error).message}</p>
      )}
    </form>
  )
}
