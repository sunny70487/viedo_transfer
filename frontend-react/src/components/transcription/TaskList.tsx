import { useTasks } from '@/hooks/use-tasks'
import { TaskCard } from './TaskCard'
import { Skeleton } from '@/components/ui/Skeleton'
import { Inbox } from 'lucide-react'

export function TaskList() {
  const { data, isLoading, isError } = useTasks()

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

  const tasks = data ? Object.values(data) : []
  const sorted = [...tasks].sort((a, b) => (b.start_time || 0) - (a.start_time || 0))

  if (sorted.length === 0) {
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
      {sorted.map((task) => (
        <TaskCard key={task.id} task={task} />
      ))}
    </div>
  )
}
