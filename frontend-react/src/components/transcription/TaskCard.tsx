import { useState, useMemo } from 'react'
import { ChevronDown, Trash2, FileText, Download, FolderInput, Eye } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Progress } from '@/components/ui/Progress'
import { useDeleteTask } from '@/hooks/use-tasks'
import { useFolders, useMoveTasksToFolder, useRemoveTasksFromFolder } from '@/hooks/use-folders'
import { useTaskStream } from '@/hooks/use-task-stream'
import { api } from '@/api/client'
import { cn, formatDuration } from '@/lib/utils'
import { TASK_STATUS } from '@/lib/constants'
import type { Task, Folder } from '@/types/api'

function buildFlatTree(folders: Folder[]): { folder: Folder; depth: number }[] {
  const childrenMap = new Map<string | null, Folder[]>()
  for (const f of folders) {
    const key = f.parent_id ?? null
    const list = childrenMap.get(key) ?? []
    list.push(f)
    childrenMap.set(key, list)
  }
  const result: { folder: Folder; depth: number }[] = []
  function walk(parentId: string | null, depth: number) {
    for (const c of childrenMap.get(parentId) ?? []) {
      result.push({ folder: c, depth })
      walk(c.id, depth + 1)
    }
  }
  walk(null, 0)
  return result
}

interface TaskCardProps {
  task: Task
}

type StatusKey = keyof typeof TASK_STATUS

function statusVariant(status: string): 'default' | 'primary' | 'success' | 'danger' | 'warning' | 'info' {
  const map: Record<string, 'default' | 'primary' | 'success' | 'danger' | 'warning' | 'info'> = {
    queued: 'default', uploading: 'info', downloading: 'info',
    processing: 'primary', transcribing: 'primary', completed: 'success', failed: 'danger',
  }
  return map[status] ?? 'default'
}

export function TaskCard({ task }: Readonly<TaskCardProps>) {
  const [expanded, setExpanded] = useState(false)
  const deleteMutation = useDeleteTask()
  const { data: folders = [] } = useFolders()
  const folderTree = useMemo(() => buildFlatTree(folders), [folders])
  const moveMutation = useMoveTasksToFolder()
  const removeMutation = useRemoveTasksFromFolder()
  const statusInfo = TASK_STATUS[task.status as StatusKey]
  const isActive = ['uploading', 'downloading', 'processing', 'transcribing', 'queued'].includes(task.status)

  useTaskStream(task.id, isActive)
  const isCompleted = task.status === 'completed'
  const isFailed = task.status === 'failed'

  const elapsed = task.start_time
    ? formatDuration(((task.end_time || Date.now() / 1000) - task.start_time))
    : ''

  const handleFolderChange = (folderId: string) => {
    if (folderId === '') {
      if (task.folder_id) {
        removeMutation.mutate({ folderId: task.folder_id, taskIds: [task.id] })
      }
    } else {
      moveMutation.mutate({ folderId, taskIds: [task.id] })
    }
  }

  return (
    <div className={cn(
      'rounded-lg border transition-colors',
      isActive ? 'border-primary/30 bg-primary/5 dark:bg-primary/5' :
      isCompleted ? 'border-green-200 dark:border-green-900/40' :
      isFailed ? 'border-red-200 dark:border-red-900/40' :
      'border-border dark:border-border-dark'
    )}>
      <div className="px-4 py-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <Badge variant={statusVariant(task.status)}>
                {statusInfo?.label ?? task.status}
              </Badge>
              {task.source_name && (
                <span className="text-sm font-medium text-text dark:text-text-dark truncate">{task.source_name}</span>
              )}
            </div>
            {task.message && (
              <p className="text-sm text-muted dark:text-muted-dark truncate">{task.message}</p>
            )}
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => {
                const msg = isActive ? '任務正在處理中，確定要取消並刪除嗎？' : '確定要刪除這個任務嗎？'
                if (globalThis.confirm(msg)) deleteMutation.mutate(task.id)
              }}
              loading={deleteMutation.isPending}
              title={isActive ? '取消任務' : '刪除'}
            >
              <Trash2 className="h-4 w-4 text-danger" />
            </Button>
            <Button variant="ghost" size="icon" onClick={() => setExpanded(!expanded)}>
              <ChevronDown className={cn('h-4 w-4 transition-transform', expanded && 'rotate-180')} />
            </Button>
          </div>
        </div>

        {isActive && task.progress != null && (
          <Progress value={task.progress} showLabel className="mt-2" />
        )}

        {elapsed && (
          <p className="text-xs text-muted dark:text-muted-dark mt-1.5">{elapsed}</p>
        )}

        {isActive && (
          <Link to={`/editor/${task.id}`} className="block mt-2">
            <Button variant="outline" size="sm" className="w-full">
              <Eye className="h-4 w-4" aria-hidden="true" />
              即時預覽字幕
            </Button>
          </Link>
        )}

        {isCompleted && (
          <Link to={`/editor/${task.id}`} className="block mt-3">
            <Button variant="primary" size="sm" className="w-full">
              <FileText className="h-4 w-4" />
              開啟字幕編輯器
            </Button>
          </Link>
        )}
      </div>

      {expanded && (
        <div className="px-4 pb-3 border-t border-border dark:border-border-dark pt-3 space-y-3 text-sm">
          <p><span className="text-muted dark:text-muted-dark">ID:</span> <span className="font-mono text-xs">{task.id}</span></p>
          {task.error && <p className="text-danger">{task.error}</p>}

          {/* Move to folder */}
          {folders.length > 0 && (
            <div className="flex items-center gap-2">
              <FolderInput className="h-4 w-4 text-muted shrink-0" />
              <select
                className="flex-1 h-8 rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark px-2 text-sm text-text dark:text-text-dark focus:outline-none focus:ring-2 focus:ring-primary/50 cursor-pointer"
                value={task.folder_id || ''}
                onChange={(e) => handleFolderChange(e.target.value)}
                disabled={moveMutation.isPending || removeMutation.isPending}
              >
                <option value="">未分類</option>
                {folderTree.map(({ folder: f, depth }) => (
                  <option key={f.id} value={f.id}>
                    {'　'.repeat(depth)}{depth > 0 ? '└ ' : ''}{f.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          {task.result?.files && (
            <div className="flex flex-wrap gap-2">
              {Object.entries(task.result.files).map(([type]) => (
                <a key={type} href={api.downloadFile(task.id, type)} download className="inline-flex items-center gap-1 px-2 py-1 rounded bg-gray-100 dark:bg-gray-800 text-xs font-medium hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors cursor-pointer">
                  <Download className="h-3 w-3" />
                  {type.toUpperCase()}
                </a>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
