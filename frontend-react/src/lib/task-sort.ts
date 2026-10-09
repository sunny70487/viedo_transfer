import type { Task } from '@/types/api'

export interface GroupedItem {
  key: string
  sortTime: number
  sortOrder: number
  sourceName: string
  watched: boolean
  type: 'single' | 'batch'
  task?: Task
  batchId?: string
  batchActiveTasks?: Task[]
  batchTotal?: number
  batchDoneCount?: number
  taskIds: string[]
}

export function naturalCompare(a: string, b: string): number {
  const re = /(\d+)|(\D+)/g
  const pa = a.match(re) ?? []
  const pb = b.match(re) ?? []
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const sa = pa[i] ?? ''
    const sb = pb[i] ?? ''
    const na = Number(sa)
    const nb = Number(sb)
    if (!isNaN(na) && !isNaN(nb)) {
      if (na !== nb) return na - nb
    } else {
      const cmp = sa.localeCompare(sb, undefined, { sensitivity: 'base' })
      if (cmp !== 0) return cmp
    }
  }
  return 0
}

/**
 * Group a folder's tasks for display. In-progress batch members collapse into
 * one batch item; finished tasks are listed individually. Watched tasks always
 * sort after unwatched ones; within each half the existing order applies
 * (custom drag order, then natural name order, then newest first).
 */
export function buildGroupedItems(taskList: Task[]): GroupedItem[] {
  const batchActive = new Map<string, Task[]>()
  const batchTotals = new Map<string, { total: number; done: number; earliest: number; minOrder: number; firstName: string }>()
  const singles: Task[] = []

  for (const t of taskList) {
    if (!t.batch_id) {
      singles.push(t)
      continue
    }
    const stats = batchTotals.get(t.batch_id) ?? { total: 0, done: 0, earliest: Infinity, minOrder: Infinity, firstName: '' }
    stats.total++
    stats.earliest = Math.min(stats.earliest, t.start_time ?? 0)
    stats.minOrder = Math.min(stats.minOrder, t.sort_order ?? 0)
    if (!stats.firstName && t.source_name) stats.firstName = t.source_name
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
    sortOrder: t.sort_order ?? 0,
    sourceName: t.source_name ?? '',
    watched: t.watched === true,
    type: 'single',
    task: t,
    taskIds: [t.id],
  }))

  for (const [batchId, activeTasks] of batchActive) {
    if (activeTasks.length === 0) continue
    const stats = batchTotals.get(batchId)!
    items.push({
      key: `batch-${batchId}`,
      sortTime: stats.earliest,
      sortOrder: stats.minOrder,
      sourceName: stats.firstName,
      watched: false,
      type: 'batch',
      batchId,
      batchActiveTasks: activeTasks,
      batchTotal: stats.total,
      batchDoneCount: stats.done,
      taskIds: activeTasks.map((t) => t.id),
    })
  }

  const hasCustomOrder = items.some((i) => i.sortOrder !== 0)
  const byWatched = (a: GroupedItem, b: GroupedItem) => Number(a.watched) - Number(b.watched)
  if (hasCustomOrder) {
    items.sort((a, b) =>
      byWatched(a, b)
      || a.sortOrder - b.sortOrder
      || naturalCompare(a.sourceName, b.sourceName)
      || b.sortTime - a.sortTime
    )
  } else {
    items.sort((a, b) => byWatched(a, b) || b.sortTime - a.sortTime)
  }
  return items
}
