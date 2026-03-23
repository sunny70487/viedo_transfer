import { useState, useRef, useCallback } from 'react'
import { Upload, FileAudio, X, Send } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { TranscriptionOptions } from './TranscriptionOptions'
import { useTranscribeUpload } from '@/hooks/use-tasks'
import { formatFileSize } from '@/lib/utils'

export function UploadForm() {
  const [file, setFile] = useState<File | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const [options, setOptions] = useState<Record<string, string>>({
    model_size: 'qwen3-asr-1.7b',
    vad_filter: 'true',
    word_timestamps: 'true',
    split_segments: 'true',
    segment_duration: '60',
  })
  const mutation = useTranscribeUpload()

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const dropped = e.dataTransfer.files[0]
    if (dropped) setFile(dropped)
  }, [])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!file) return
    mutation.mutate({ file, params: options })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div
        className={`relative border-2 border-dashed rounded-xl p-8 text-center transition-colors cursor-pointer ${
          dragOver
            ? 'border-primary bg-primary/5'
            : 'border-border dark:border-border-dark hover:border-primary/50'
        }`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept="audio/*,video/*,.mp3,.wav,.flac,.m4a,.ogg,.mp4,.avi,.mkv,.webm,.mov"
          className="hidden"
          onChange={(e) => e.target.files?.[0] && setFile(e.target.files[0])}
        />
        {file ? (
          <div className="flex items-center justify-center gap-3">
            <FileAudio className="h-8 w-8 text-primary" />
            <div className="text-left">
              <p className="font-medium text-text dark:text-text-dark">{file.name}</p>
              <p className="text-sm text-muted dark:text-muted-dark">{formatFileSize(file.size)}</p>
            </div>
            <Button type="button" variant="ghost" size="icon" onClick={(e) => { e.stopPropagation(); setFile(null) }}>
              <X className="h-4 w-4" />
            </Button>
          </div>
        ) : (
          <>
            <Upload className="h-10 w-10 mx-auto text-muted dark:text-muted-dark mb-3" />
            <p className="text-sm font-medium text-text dark:text-text-dark">拖拽檔案到此處或點擊選取</p>
            <p className="text-xs text-muted dark:text-muted-dark mt-1">支援 MP3, WAV, FLAC, MP4, AVI, MKV 等格式</p>
          </>
        )}
      </div>
      <TranscriptionOptions values={options} onChange={(k, v) => setOptions((p) => ({ ...p, [k]: v }))} />
      <Button type="submit" className="w-full" disabled={!file} loading={mutation.isPending}>
        <Send className="h-4 w-4" />
        上傳並轉錄
      </Button>
      {mutation.isError && (
        <p className="text-sm text-danger">{(mutation.error as Error).message}</p>
      )}
    </form>
  )
}
