import { useState } from 'react'
import { ChevronDown, Trash2, ExternalLink, Download } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Progress } from '@/components/ui/Progress'
import { useDeleteTask } from '@/hooks/use-tasks'
import { api } from '@/api/client'
import { cn, formatDuration } from '@/lib/utils'
import { TASK_STATUS } from '@/lib/constants'
import type { Task } from '@/types/api'

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

export function TaskCard({ task }: TaskCardProps) {
  const [expanded, setExpanded] = useState(false)
  const deleteMutation = useDeleteTask()
  const statusInfo = TASK_STATUS[task.status as StatusKey]
  const isActive = ['uploading', 'downloading', 'processing', 'transcribing', 'queued'].includes(task.status)
  const isCompleted = task.status === 'completed'
  const isFailed = task.status === 'failed'

  const elapsed = task.start_time
    ? formatDuration(((task.end_time || Date.now() / 1000) - task.start_time))
    : ''

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
            {isCompleted && (
              <Link to={`/editor/${task.id}`}>
                <Button variant="ghost" size="icon" title="編輯字幕">
                  <ExternalLink className="h-4 w-4" />
                </Button>
              </Link>
            )}
            {(isCompleted || isFailed) && (
              <Button
                variant="ghost"
                size="icon"
                onClick={() => deleteMutation.mutate(task.id)}
                loading={deleteMutation.isPending}
                title="刪除"
              >
                <Trash2 className="h-4 w-4 text-danger" />
              </Button>
            )}
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
      </div>

      {expanded && (
        <div className="px-4 pb-3 border-t border-border dark:border-border-dark pt-3 space-y-2 text-sm">
          <p><span className="text-muted dark:text-muted-dark">ID:</span> <span className="font-mono text-xs">{task.id}</span></p>
          {task.error && <p className="text-danger">{task.error}</p>}
          {task.result?.files && (
            <div className="flex flex-wrap gap-2 mt-2">
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
