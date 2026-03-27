import { useMemo } from 'react'
import { useTasks } from '@/hooks/use-tasks'
import { TaskCard } from './TaskCard'
import { BatchProgressCard } from './BatchProgressCard'
import { Skeleton } from '@/components/ui/Skeleton'
import { Inbox } from 'lucide-react'
import type { Task } from '@/types/api'

interface GroupedItem {
  key: string
  sortTime: number
  type: 'single' | 'batch'
  task?: Task
  batchId?: string
  batchActiveTasks?: Task[]
  batchTotal?: number
  batchDoneCount?: number
}

function groupTasks(taskMap: Record<string, Task>): GroupedItem[] {
  const all = Object.values(taskMap)
  const batchActive = new Map<string, Task[]>()
  const batchTotals = new Map<string, { total: number; done: number; earliest: number }>()
  const singles: Task[] = []

  for (const t of all) {
    if (!t.batch_id) {
      singles.push(t)
      continue
    }

    const stats = batchTotals.get(t.batch_id) ?? { total: 0, done: 0, earliest: Infinity }
    stats.total++
    stats.earliest = Math.min(stats.earliest, t.start_time ?? 0)

    const isDone = t.status === 'completed' || t.status === 'failed'
    if (isDone) {
      stats.done++
      singles.push(t)
    } else {
      const list = batchActive.get(t.batch_id) ?? []
      list.push(t)
      batchActive.set(t.batch_id, list)
    }
    batchTotals.set(t.batch_id, stats)
  }

  const items: GroupedItem[] = singles.map((t) => ({
    key: t.id,
    sortTime: t.start_time ?? 0,
    type: 'single',
    task: t,
  }))

  for (const [batchId, activeTasks] of batchActive) {
    if (activeTasks.length === 0) continue
    const stats = batchTotals.get(batchId)!
    items.push({
      key: `batch-${batchId}`,
      sortTime: stats.earliest,
      type: 'batch',
      batchId,
      batchActiveTasks: activeTasks,
      batchTotal: stats.total,
      batchDoneCount: stats.done,
    })
  }

  items.sort((a, b) => b.sortTime - a.sortTime)
  return items
}

export function TaskList() {
  const { data, isLoading, isError } = useTasks()

  const items = useMemo(() => (data ? groupTasks(data) : []), [data])

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-24 w-full rounded-lg" />
        ))}
      </div>
    )
  }

  if (isError) {
    return <p className="text-center text-danger py-8">無法載入任務列表</p>
  }

  if (items.length === 0) {
    return (
      <div className="text-center py-12">
        <Inbox className="h-12 w-12 mx-auto text-muted/40 dark:text-muted-dark/40 mb-3" />
        <p className="text-muted dark:text-muted-dark font-medium">尚無任務</p>
        <p className="text-sm text-muted/70 dark:text-muted-dark/70 mt-1">提交 URL 或上傳檔案以開始轉錄</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {items.map((item) =>
        item.type === 'batch' ? (
          <BatchProgressCard
            key={item.key}
            batchId={item.batchId!}
            activeTasks={item.batchActiveTasks!}
            batchTotal={item.batchTotal!}
            batchDoneCount={item.batchDoneCount!}
          />
        ) : (
          <TaskCard key={item.key} task={item.task!} />
        ),
      )}
    </div>
  )
}
