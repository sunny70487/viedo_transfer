import { useState, useRef, useCallback } from 'react'
import { Upload, FileAudio, X, Send } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { TranscriptionOptions } from './TranscriptionOptions'
import { useTranscribeUpload, useTranscribeBatchUpload } from '@/hooks/use-tasks'
import { formatFileSize } from '@/lib/utils'

export function UploadForm() {
  const [files, setFiles] = useState<File[]>([])
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const [options, setOptions] = useState<Record<string, string>>({
    model_size: 'qwen3-asr-1.7b',
    vad_filter: 'true',
    word_timestamps: 'true',
    split_segments: 'true',
    segment_duration: '60',
  })
  const singleMutation = useTranscribeUpload()
  const batchMutation = useTranscribeBatchUpload()

  const isBatch = files.length > 1
  const isPending = singleMutation.isPending || batchMutation.isPending

  const addFiles = useCallback((incoming: FileList | File[]) => {
    const arr = Array.from(incoming)
    setFiles((prev) => {
      const existing = new Set(prev.map((f) => `${f.name}-${f.size}-${f.lastModified}`))
      const unique = arr.filter((f) => !existing.has(`${f.name}-${f.size}-${f.lastModified}`))
      return [...prev, ...unique]
    })
  }, [])

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index))
  }

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    if (e.dataTransfer.files.length > 0) addFiles(e.dataTransfer.files)
  }, [addFiles])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (files.length === 0) return
    if (isBatch) {
      batchMutation.mutate({ files, params: options }, {
        onSuccess: () => setFiles([]),
      })
    } else {
      singleMutation.mutate({ file: files[0], params: options }, {
        onSuccess: () => setFiles([]),
      })
    }
  }

  const totalSize = files.reduce((sum, f) => sum + f.size, 0)

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
          multiple
          accept="audio/*,video/*,.mp3,.wav,.flac,.m4a,.ogg,.mp4,.avi,.mkv,.webm,.mov"
          className="hidden"
          onChange={(e) => {
            if (e.target.files) addFiles(e.target.files)
            e.target.value = ''
          }}
        />
        {files.length > 0 ? (
          <div className="space-y-2" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-text dark:text-text-dark">
                {files.length} 個檔案（{formatFileSize(totalSize)}）
              </span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setFiles([])}
                className="text-xs"
              >
                清除全部
              </Button>
            </div>
            <div className="max-h-40 overflow-y-auto space-y-1">
              {files.map((file, i) => (
                <div key={`${file.name}-${file.size}-${i}`} className="flex items-center gap-2 px-2 py-1.5 rounded-lg bg-gray-50 dark:bg-gray-800/50">
                  <FileAudio className="h-4 w-4 text-primary shrink-0" />
                  <span className="text-sm text-text dark:text-text-dark truncate flex-1">{file.name}</span>
                  <span className="text-xs text-muted dark:text-muted-dark shrink-0">{formatFileSize(file.size)}</span>
                  <button
                    type="button"
                    className="p-0.5 rounded hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors cursor-pointer"
                    onClick={() => removeFile(i)}
                  >
                    <X className="h-3.5 w-3.5 text-muted" />
                  </button>
                </div>
              ))}
            </div>
            <button
              type="button"
              className="text-xs text-primary hover:underline cursor-pointer mt-1"
              onClick={() => inputRef.current?.click()}
            >
              + 新增更多檔案
            </button>
          </div>
        ) : (
          <>
            <Upload className="h-10 w-10 mx-auto text-muted dark:text-muted-dark mb-3" />
            <p className="text-sm font-medium text-text dark:text-text-dark">拖拽檔案到此處或點擊選取</p>
            <p className="text-xs text-muted dark:text-muted-dark mt-1">支援多檔案上傳 · MP3, WAV, FLAC, MP4, AVI, MKV 等</p>
          </>
        )}
      </div>
      <TranscriptionOptions values={options} onChange={(k, v) => setOptions((p) => ({ ...p, [k]: v }))} />
      <Button type="submit" className="w-full" disabled={files.length === 0} loading={isPending}>
        <Send className="h-4 w-4" />
        {isBatch ? `批次上傳並轉錄 (${files.length} 個)` : '上傳並轉錄'}
      </Button>
      {(singleMutation.isError || batchMutation.isError) && (
        <p className="text-sm text-danger">
          {((singleMutation.error || batchMutation.error) as Error)?.message}
        </p>
      )}
    </form>
  )
}
