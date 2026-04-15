import { useState } from 'react'
import { Link2, Send } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Select } from '@/components/ui/Select'
import { TranscriptionOptions } from './TranscriptionOptions'
import { FolderSelect } from './FolderSelect'
import { useTranscribeUrl, useTranscribeBatchUrls } from '@/hooks/use-tasks'

const FORMAT_OPTIONS = [
  { value: 'audio', label: '僅音檔' },
  { value: 'video', label: '影片' },
  { value: 'both', label: '兩者' },
]

function parseUrls(text: string): string[] {
  return text
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
}

export function URLForm() {
  const [urlText, setUrlText] = useState('')
  const [downloadFormat, setDownloadFormat] = useState('both')
  const [selectedFolderId, setSelectedFolderId] = useState('')
  const [options, setOptions] = useState<Record<string, string>>({
    model_size: 'qwen3-asr-1.7b',
    vad_filter: 'true',
    word_timestamps: 'true',
    split_segments: 'true',
    segment_duration: '60',
  })
  const singleMutation = useTranscribeUrl()
  const batchMutation = useTranscribeBatchUrls()

  const urls = parseUrls(urlText)
  const isBatch = urls.length > 1
  const isPending = singleMutation.isPending || batchMutation.isPending

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (urls.length === 0) return

    const shared: Record<string, unknown> = Object.fromEntries(
      Object.entries(options).filter(([, v]) => v !== ''),
    )
    if (selectedFolderId) shared.folder_id = selectedFolderId

    if (isBatch) {
      batchMutation.mutate({
        urls,
        download_format: downloadFormat,
        ...shared,
      })
    } else {
      singleMutation.mutate({
        url: urls[0],
        download_format: downloadFormat,
        ...shared,
      })
    }
    setUrlText('')
  }

  const handleOptionChange = (key: string, value: string) => {
    setOptions((prev) => ({ ...prev, [key]: value }))
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label htmlFor="url-input" className="block text-sm font-medium text-text dark:text-text-dark">URL</label>
          {urls.length > 0 && (
            <span className="text-xs text-muted dark:text-muted-dark">
              {urls.length} 個 URL{isBatch ? '（批次模式）' : ''}
            </span>
          )}
        </div>
        <div className="relative">
          <Link2 className="absolute left-3 top-3 h-4 w-4 text-muted" />
          <textarea
            id="url-input"
            value={urlText}
            onChange={(e) => setUrlText(e.target.value)}
            placeholder={'YouTube、Bilibili 或直接音檔/影片連結\n多個 URL 請每行輸入一個'}
            className="w-full pl-10 pr-3 py-2 text-sm rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark text-text dark:text-text-dark placeholder:text-muted/60 focus:outline-none focus:ring-2 focus:ring-primary/40 resize-y min-h-[42px]"
            rows={urls.length > 1 ? Math.min(urls.length + 1, 6) : 1}
          />
        </div>
      </div>
      <div>
        <label className="block text-sm font-medium text-text dark:text-text-dark mb-1.5">下載格式</label>
        <Select options={FORMAT_OPTIONS} value={downloadFormat} onChange={(e) => setDownloadFormat(e.target.value)} />
      </div>
      <FolderSelect value={selectedFolderId} onChange={setSelectedFolderId} />
      <TranscriptionOptions values={options} onChange={handleOptionChange} />
      <Button type="submit" className="w-full" loading={isPending} disabled={urls.length === 0}>
        <Send className="h-4 w-4" />
        {isBatch ? `批次轉錄 (${urls.length} 個)` : '開始轉錄'}
      </Button>
      {(singleMutation.isError || batchMutation.isError) && (
        <p className="text-sm text-danger">
          {((singleMutation.error || batchMutation.error) as Error)?.message}
        </p>
      )}
    </form>
  )
}
