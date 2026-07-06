import { useState, useRef, useEffect } from 'react'
import {
  FolderOpen, FolderClosed, ChevronDown, ChevronRight,
  MoreHorizontal, Pencil, Trash2, FolderPlus, Download,
} from 'lucide-react'
import { Badge } from '@/components/ui/Badge'
import { useRenameFolder, useDeleteFolder, useCreateFolder } from '@/hooks/use-folders'
import { cn } from '@/lib/utils'
import { api } from '@/api/client'

const SUBTITLE_FORMATS = ['srt', 'vtt', 'txt', 'ass', 'json'] as const

interface FolderGroupHeaderProps {
  folderId: string | null
  folderName: string
  taskCount: number
  isExpanded: boolean
  onToggle: () => void
  depth?: number
}

export function FolderGroupHeader({
  folderId,
  folderName,
  taskCount,
  isExpanded,
  onToggle,
  depth = 0,
}: Readonly<FolderGroupHeaderProps>) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [nameValue, setNameValue] = useState(folderName)
  const [creatingChild, setCreatingChild] = useState(false)
  const [childName, setChildName] = useState('')
  const [showFormats, setShowFormats] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const childInputRef = useRef<HTMLInputElement>(null)

  const renameMutation = useRenameFolder()
  const deleteMutation = useDeleteFolder()
  const createChildMutation = useCreateFolder()

  const isUncategorized = folderId === null

  useEffect(() => {
    if (!menuOpen) return
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [menuOpen])

  useEffect(() => {
    if (renaming) inputRef.current?.focus()
  }, [renaming])

  useEffect(() => {
    if (creatingChild) childInputRef.current?.focus()
  }, [creatingChild])

  const handleRename = () => {
    const trimmed = nameValue.trim()
    if (!trimmed || !folderId || trimmed === folderName) {
      setRenaming(false)
      setNameValue(folderName)
      return
    }
    renameMutation.mutate(
      { folderId, name: trimmed },
      { onSuccess: () => setRenaming(false) },
    )
  }

  const handleDelete = () => {
    if (!folderId) return
    if (!globalThis.confirm(`確定要刪除資料夾「${folderName}」嗎？\n資料夾內的所有任務也會一併刪除。`)) return
    setMenuOpen(false)
    deleteMutation.mutate(folderId)
  }

  const handleCreateChild = () => {
    const trimmed = childName.trim()
    if (!trimmed || !folderId) {
      setCreatingChild(false)
      setChildName('')
      return
    }
    createChildMutation.mutate(
      { name: trimmed, parentId: folderId },
      { onSuccess: () => { setCreatingChild(false); setChildName('') } },
    )
  }

  const handleDownloadSubtitles = (format: string) => {
    if (!folderId) return
    setMenuOpen(false)
    setShowFormats(false)
    globalThis.location.href = api.downloadFolderSubtitles(folderId, format)
  }

  return (
    <div>
      <div className={cn(
        'flex items-center gap-2 px-3 py-2.5 rounded-lg',
        depth === 0
          ? 'bg-gray-50/80 dark:bg-gray-800/40'
          : 'bg-gray-50/50 dark:bg-gray-800/20',
      )}>
        <button
          type="button"
          className="flex items-center gap-2 flex-1 min-w-0 cursor-pointer"
          onClick={onToggle}
        >
          {isExpanded
            ? <ChevronDown className="h-4 w-4 text-muted shrink-0" />
            : <ChevronRight className="h-4 w-4 text-muted shrink-0" />}
          {isExpanded
            ? <FolderOpen className="h-4 w-4 text-amber-500 shrink-0" />
            : <FolderClosed className="h-4 w-4 text-amber-500 shrink-0" />}

          {renaming ? (
            <input
              ref={inputRef}
              className="flex-1 min-w-0 text-sm font-medium bg-white dark:bg-gray-900 border border-primary rounded px-2 py-0.5 text-text dark:text-text-dark focus:outline-none focus:ring-2 focus:ring-primary/50"
              value={nameValue}
              onChange={(e) => setNameValue(e.target.value)}
              onBlur={handleRename}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleRename()
                if (e.key === 'Escape') { setRenaming(false); setNameValue(folderName) }
              }}
              onClick={(e) => e.stopPropagation()}
            />
          ) : (
            <span className={cn(
              'text-sm font-medium truncate',
              isUncategorized ? 'text-muted dark:text-muted-dark' : 'text-text dark:text-text-dark',
            )}>
              {folderName}
            </span>
          )}
        </button>

        <Badge variant="default" className="shrink-0">{taskCount}</Badge>

        {!isUncategorized && (
          <div className="relative" ref={menuRef}>
            <button
              type="button"
              className="p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors cursor-pointer"
              onClick={(e) => { e.stopPropagation(); setShowFormats(false); setMenuOpen(!menuOpen) }}
            >
              <MoreHorizontal className="h-4 w-4 text-muted" />
            </button>
            {menuOpen && (
              <div className="absolute right-0 top-full mt-1 z-20 w-44 bg-surface dark:bg-surface-dark border border-border dark:border-border-dark rounded-lg shadow-lg py-1">
                <div className="relative">
                  <button
                    type="button"
                    className="w-full flex items-center justify-between gap-2 px-3 py-2 text-sm text-text dark:text-text-dark hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors cursor-pointer"
                    onClick={() => setShowFormats((v) => !v)}
                  >
                    <span className="flex items-center gap-2">
                      <Download className="h-3.5 w-3.5" />
                      下載字幕
                    </span>
                    <ChevronRight className="h-3.5 w-3.5 text-muted" />
                  </button>
                  {showFormats && (
                    <div className="mt-0.5 ml-6 border-l border-border dark:border-border-dark pl-2 py-0.5">
                      {SUBTITLE_FORMATS.map((fmt) => (
                        <button
                          key={fmt}
                          type="button"
                          className="w-full text-left px-3 py-1.5 text-xs text-text dark:text-text-dark hover:bg-gray-100 dark:hover:bg-gray-800 rounded transition-colors cursor-pointer uppercase"
                          onClick={() => handleDownloadSubtitles(fmt)}
                        >
                          {fmt}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <button
                  type="button"
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm text-text dark:text-text-dark hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors cursor-pointer"
                  onClick={() => { setMenuOpen(false); setCreatingChild(true) }}
                >
                  <FolderPlus className="h-3.5 w-3.5" />
                  新增子資料夾
                </button>
                <button
                  type="button"
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm text-text dark:text-text-dark hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors cursor-pointer"
                  onClick={() => { setMenuOpen(false); setRenaming(true) }}
                >
                  <Pencil className="h-3.5 w-3.5" />
                  重命名
                </button>
                <button
                  type="button"
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm text-danger hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors cursor-pointer"
                  onClick={handleDelete}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  刪除資料夾
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {creatingChild && (
        <div className="flex items-center gap-2 mt-1.5 pl-8">
          <FolderPlus className="h-4 w-4 text-muted shrink-0" />
          <input
            ref={childInputRef}
            className="flex-1 min-w-0 h-8 text-sm bg-white dark:bg-gray-900 border border-primary rounded-lg px-2 text-text dark:text-text-dark focus:outline-none focus:ring-2 focus:ring-primary/50"
            placeholder="子資料夾名稱"
            value={childName}
            onChange={(e) => setChildName(e.target.value)}
            onBlur={handleCreateChild}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleCreateChild()
              if (e.key === 'Escape') { setCreatingChild(false); setChildName('') }
            }}
          />
        </div>
      )}
    </div>
  )
}
