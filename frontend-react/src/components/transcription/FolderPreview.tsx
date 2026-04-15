import { useState, useMemo } from 'react'
import {
  FolderOpen, FileAudio, FileVideo, ChevronDown, ChevronRight,
  X, Send, ArrowLeft, Pencil,
} from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { TranscriptionOptions } from './TranscriptionOptions'
import { useTranscribeFolderUpload } from '@/hooks/use-folders'
import { formatFileSize } from '@/lib/utils'

const SUPPORTED_EXTENSIONS = new Set([
  '.mp3', '.wav', '.ogg', '.flac', '.aac',
  '.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v', '.mpeg', '.mpg',
])

const VIDEO_EXTENSIONS = new Set([
  '.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v', '.mpeg', '.mpg',
])

function getExtension(name: string): string {
  const dot = name.lastIndexOf('.')
  return dot >= 0 ? name.slice(dot).toLowerCase() : ''
}

interface FolderFile {
  file: File
  relativePath: string
  directory: string
  supported: boolean
  selected: boolean
}

interface SubfolderGroup {
  path: string
  files: FolderFile[]
}

interface FolderPreviewProps {
  files: File[]
  rootFolderName: string
  onCancel: () => void
  onSubmitted: () => void
}

export function FolderPreview({ files, rootFolderName, onCancel, onSubmitted }: Readonly<FolderPreviewProps>) {
  const folderUpload = useTranscribeFolderUpload()

  const [folderName, setFolderName] = useState(rootFolderName)
  const [editingName, setEditingName] = useState(false)
  const [options, setOptions] = useState<Record<string, string>>({
    model_size: 'qwen3-asr-1.7b',
    vad_filter: 'true',
    word_timestamps: 'true',
    split_segments: 'true',
    segment_duration: '60',
  })

  const folderFiles = useMemo<FolderFile[]>(() => {
    return files.map((f) => {
      const rel = (f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name
      const parts = rel.split('/')
      const dir = parts.length > 2 ? parts.slice(1, -1).join('/') : ''
      const ext = getExtension(f.name)
      return {
        file: f,
        relativePath: rel,
        directory: dir,
        supported: SUPPORTED_EXTENSIONS.has(ext),
        selected: SUPPORTED_EXTENSIONS.has(ext),
      }
    })
  }, [files])

  const [selection, setSelection] = useState<Record<string, boolean>>(() => {
    const map: Record<string, boolean> = {}
    folderFiles.forEach((ff) => {
      if (ff.supported) map[ff.relativePath] = true
    })
    return map
  })

  const toggleFile = (path: string) => {
    setSelection((prev) => ({ ...prev, [path]: !prev[path] }))
  }

  const toggleAll = (selected: boolean) => {
    setSelection((prev) => {
      const next = { ...prev }
      folderFiles.forEach((ff) => {
        if (ff.supported) next[ff.relativePath] = selected
      })
      return next
    })
  }

  const subfolders = useMemo<SubfolderGroup[]>(() => {
    const groups = new Map<string, FolderFile[]>()
    for (const ff of folderFiles) {
      if (!ff.supported) continue
      const key = ff.directory || '(根目錄)'
      const list = groups.get(key) ?? []
      list.push(ff)
      groups.set(key, list)
    }
    return Array.from(groups.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([path, groupFiles]) => ({ path, files: groupFiles }))
  }, [folderFiles])

  const [expanded, setExpanded] = useState<Record<string, boolean>>(() => {
    const map: Record<string, boolean> = {}
    subfolders.forEach((g) => { map[g.path] = true })
    return map
  })

  const totalSupported = folderFiles.filter((f) => f.supported).length
  const totalUnsupported = folderFiles.length - totalSupported
  const selectedCount = Object.values(selection).filter(Boolean).length
  const selectedFiles = folderFiles.filter((ff) => ff.supported && selection[ff.relativePath])
  const selectedSize = selectedFiles.reduce((s, ff) => s + ff.file.size, 0)

  const handleSubmit = () => {
    if (selectedCount === 0) return
    const submitFiles = selectedFiles.map((ff) => ff.file)
    const paths = selectedFiles.map((ff) => ff.relativePath)
    folderUpload.mutate(
      { files: submitFiles, relativePaths: paths, folderName, params: options },
      { onSuccess: () => onSubmitted() },
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Button type="button" variant="ghost" size="icon" onClick={onCancel} title="返回">
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <FolderOpen className="h-5 w-5 text-primary" />
        {editingName ? (
          <Input
            autoFocus
            className="flex-1 h-8 text-sm"
            value={folderName}
            onChange={(e) => setFolderName(e.target.value)}
            onBlur={() => setEditingName(false)}
            onKeyDown={(e) => { if (e.key === 'Enter') setEditingName(false) }}
          />
        ) : (
          <button
            type="button"
            className="flex items-center gap-1.5 text-sm font-semibold text-text dark:text-text-dark hover:text-primary transition-colors cursor-pointer"
            onClick={() => setEditingName(true)}
          >
            {folderName}
            <Pencil className="h-3 w-3 text-muted" />
          </button>
        )}
      </div>

      <div className="flex items-center justify-between text-xs text-muted dark:text-muted-dark">
        <span>
          已選取 {selectedCount} / {totalSupported} 個媒體檔案
          （{formatFileSize(selectedSize)}）
          {totalUnsupported > 0 && (
            <span className="text-amber-500 ml-1">· {totalUnsupported} 個不支援的檔案已略過</span>
          )}
        </span>
        <div className="flex gap-2">
          <button type="button" className="text-primary hover:underline cursor-pointer" onClick={() => toggleAll(true)}>全選</button>
          <button type="button" className="text-primary hover:underline cursor-pointer" onClick={() => toggleAll(false)}>取消全選</button>
        </div>
      </div>

      <div className="max-h-64 overflow-y-auto border border-border dark:border-border-dark rounded-lg divide-y divide-border dark:divide-border-dark">
        {subfolders.map((group) => {
          const groupSelected = group.files.filter((f) => selection[f.relativePath]).length
          const isExpanded = expanded[group.path] ?? true
          return (
            <div key={group.path}>
              <button
                type="button"
                className="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors cursor-pointer"
                onClick={() => setExpanded((p) => ({ ...p, [group.path]: !isExpanded }))}
              >
                {isExpanded ? <ChevronDown className="h-3.5 w-3.5 text-muted shrink-0" /> : <ChevronRight className="h-3.5 w-3.5 text-muted shrink-0" />}
                <FolderOpen className="h-4 w-4 text-amber-500 shrink-0" />
                <span className="font-medium text-text dark:text-text-dark truncate">{group.path}</span>
                <span className="text-xs text-muted dark:text-muted-dark shrink-0 ml-auto">
                  {groupSelected}/{group.files.length}
                </span>
              </button>
              {isExpanded && (
                <div className="pl-10 pr-3 pb-1 space-y-0.5">
                  {group.files.map((ff) => {
                    const ext = getExtension(ff.file.name)
                    const isVideo = VIDEO_EXTENSIONS.has(ext)
                    const isChecked = selection[ff.relativePath] ?? false
                    return (
                      <label
                        key={ff.relativePath}
                        className="flex items-center gap-2 py-1 px-1 rounded hover:bg-gray-50 dark:hover:bg-gray-800/30 cursor-pointer"
                      >
                        <input
                          type="checkbox"
                          className="rounded cursor-pointer"
                          checked={isChecked}
                          onChange={() => toggleFile(ff.relativePath)}
                        />
                        {isVideo
                          ? <FileVideo className="h-4 w-4 text-blue-500 shrink-0" />
                          : <FileAudio className="h-4 w-4 text-primary shrink-0" />}
                        <span className="text-sm text-text dark:text-text-dark truncate flex-1">{ff.file.name}</span>
                        <span className="text-xs text-muted dark:text-muted-dark shrink-0">{formatFileSize(ff.file.size)}</span>
                      </label>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}
        {subfolders.length === 0 && (
          <div className="px-4 py-8 text-center text-muted dark:text-muted-dark text-sm">
            此資料夾中未找到支援的媒體檔案
          </div>
        )}
      </div>

      <TranscriptionOptions values={options} onChange={(k, v) => setOptions((p) => ({ ...p, [k]: v }))} />

      <div className="flex gap-2">
        <Button type="button" variant="outline" className="flex-1" onClick={onCancel}>
          <X className="h-4 w-4" />
          取消
        </Button>
        <Button
          type="button"
          className="flex-1"
          disabled={selectedCount === 0}
          loading={folderUpload.isPending}
          onClick={handleSubmit}
        >
          <Send className="h-4 w-4" />
          開始轉譯 ({selectedCount} 個檔案)
        </Button>
      </div>
      {folderUpload.isError && (
        <p className="text-sm text-danger">{(folderUpload.error as Error)?.message}</p>
      )}
    </div>
  )
}
