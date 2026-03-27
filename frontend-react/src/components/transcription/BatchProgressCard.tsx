import { useState } from 'react'
import { ChevronDown, Layers } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Progress } from '@/components/ui/Progress'
import { TaskCard } from './TaskCard'
import { cn } from '@/lib/utils'
import type { Task } from '@/types/api'

interface BatchProgressCardProps {
  batchId: string
  activeTasks: Task[]
  batchTotal: number
  batchDoneCount: number
}

export function BatchProgressCard({
  batchId,
  activeTasks,
  batchTotal,
  batchDoneCount,
}: Readonly<BatchProgressCardProps>) {
  const [expanded, setExpanded] = useState(false)
  const sorted = [...activeTasks].sort((a, b) => (a.start_time ?? 0) - (b.start_time ?? 0))

  let processing = 0
  let queued = 0
  let activeProgress = 0
  for (const t of activeTasks) {
    activeProgress += t.progress ?? 0
    if (t.status === 'queued') queued++
    else processing++
  }

  const overallProgress = batchTotal > 0
    ? ((batchDoneCount * 100) + activeProgress) / batchTotal
    : 0

  return (
    <div className={cn('rounded-lg border transition-colors border-primary/30 bg-primary/5 dark:bg-primary/5')}>
      <div className="px-4 py-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <Layers className="h-4 w-4 text-primary shrink-0" />
              <Badge variant="info">
                批次 · {batchDoneCount}/{batchTotal} 已完成
              </Badge>
            </div>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted dark:text-muted-dark">
              {processing > 0 && <span className="text-primary">{processing} 處理中</span>}
              {queued > 0 && <span>{queued} 佇列中</span>}
            </div>
          </div>
          <Button variant="ghost" size="icon" onClick={() => setExpanded(!expanded)}>
            <ChevronDown className={cn('h-4 w-4 transition-transform', expanded && 'rotate-180')} />
          </Button>
        </div>

        <Progress value={overallProgress} showLabel className="mt-2" />
      </div>

      {expanded && (
        <div className="px-3 pb-3 border-t border-border dark:border-border-dark pt-3 space-y-2">
          <p className="text-xs text-muted dark:text-muted-dark px-1 mb-1">
            批次 ID: <span className="font-mono">{batchId.slice(0, 8)}</span>
          </p>
          {sorted.map((task) => (
            <TaskCard key={task.id} task={task} />
          ))}
        </div>
      )}
    </div>
  )
}
