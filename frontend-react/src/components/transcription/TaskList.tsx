import { useMemo, useState, useCallback } from 'react'
import {
  DndContext,
  closestCenter,
  PointerSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  useSortable,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { useTasks, useDeleteAllFailedTasks } from '@/hooks/use-tasks'
import { useFolders, useCreateFolder, useReorderTasks } from '@/hooks/use-folders'
import { useTaskNotifications } from '@/hooks/use-task-notifications'
import { TaskCard } from './TaskCard'
import { BatchProgressCard } from './BatchProgressCard'
import { FolderGroupHeader } from './FolderGroupHeader'
import { Skeleton } from '@/components/ui/Skeleton'
import { Inbox, FolderPlus, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import type { Task, Folder } from '@/types/api'

const EXPANDED_STORAGE_KEY = 'whisper_folder_expanded'

function loadExpanded(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(EXPANDED_STORAGE_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch { return {} }
}

function saveExpanded(state: Record<string, boolean>) {
  try { localStorage.setItem(EXPANDED_STORAGE_KEY, JSON.stringify(state)) } catch { /* ignore */ }
}

// ---------------------------------------------------------------------------
// Grouped items (batch merging logic)
// ---------------------------------------------------------------------------
interface GroupedItem {
  key: string
  sortTime: number
  sortOrder: number
  sourceName: string
  type: 'single' | 'batch'
  task?: Task
  batchId?: string
  batchActiveTasks?: Task[]
  batchTotal?: number
  batchDoneCount?: number
  taskIds: string[]
}

function naturalCompare(a: string, b: string): number {
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

function buildGroupedItems(taskList: Task[]): GroupedItem[] {
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
      type: 'batch',
      batchId,
      batchActiveTasks: activeTasks,
      batchTotal: stats.total,
      batchDoneCount: stats.done,
      taskIds: activeTasks.map((t) => t.id),
    })
  }

  const hasCustomOrder = items.some((i) => i.sortOrder !== 0)
  if (hasCustomOrder) {
    items.sort((a, b) =>
      a.sortOrder - b.sortOrder
      || naturalCompare(a.sourceName, b.sourceName)
      || b.sortTime - a.sortTime
    )
  } else {
    items.sort((a, b) => b.sortTime - a.sortTime)
  }
  return items
}

// ---------------------------------------------------------------------------
// Folder tree node
// ---------------------------------------------------------------------------
interface FolderNode {
  folder: Folder
  children: FolderNode[]
  tasks: Task[]
}

function buildFolderTree(
  folders: Folder[],
  tasksByFolder: Map<string, Task[]>,
): FolderNode[] {
  const nodeMap = new Map<string, FolderNode>()
  for (const f of folders) {
    nodeMap.set(f.id, { folder: f, children: [], tasks: tasksByFolder.get(f.id) ?? [] })
  }

  const roots: FolderNode[] = []
  for (const f of folders) {
    const node = nodeMap.get(f.id)!
    if (f.parent_id && nodeMap.has(f.parent_id)) {
      nodeMap.get(f.parent_id)!.children.push(node)
    } else {
      roots.push(node)
    }
  }

  roots.sort((a, b) => a.folder.sort_order - b.folder.sort_order)
  for (const node of nodeMap.values()) {
    node.children.sort((a, b) => a.folder.sort_order - b.folder.sort_order)
  }

  return roots
}

// ---------------------------------------------------------------------------
// Sortable task item
// ---------------------------------------------------------------------------
function SortableTaskItem({ item }: Readonly<{ item: GroupedItem }>) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: item.key })
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    zIndex: isDragging ? 10 : undefined,
  }

  return (
    <div ref={setNodeRef} style={style} {...attributes} {...listeners} className="touch-none">
      {item.type === 'batch' ? (
        <BatchProgressCard
          batchId={item.batchId!}
          activeTasks={item.batchActiveTasks!}
          batchTotal={item.batchTotal!}
          batchDoneCount={item.batchDoneCount!}
        />
      ) : (
        <TaskCard task={item.task!} />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Recursive folder group renderer
// ---------------------------------------------------------------------------
function FolderGroupContent({
  node,
  depth,
  expanded,
  onToggle,
  onReorder,
}: Readonly<{
  node: FolderNode
  depth: number
  expanded: Record<string, boolean>
  onToggle: (key: string) => void
  onReorder: (folderId: string, taskIds: string[]) => void
}>) {
  const items = useMemo(() => buildGroupedItems(node.tasks), [node.tasks])
  const itemKeys = useMemo(() => items.map((i) => i.key), [items])
  const isExpanded = expanded[node.folder.id] ?? true
  const totalCount = items.length + node.children.reduce((s, c) => s + countDescendantTasks(c), 0)

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event
      if (!over || active.id === over.id) return
      const oldIndex = itemKeys.indexOf(active.id as string)
      const newIndex = itemKeys.indexOf(over.id as string)
      if (oldIndex === -1 || newIndex === -1) return
      const reordered = [...itemKeys]
      reordered.splice(oldIndex, 1)
      reordered.splice(newIndex, 0, active.id as string)

      const allTaskIds: string[] = []
      for (const key of reordered) {
        const item = items.find((i) => i.key === key)
        if (item) allTaskIds.push(...item.taskIds)
      }
      onReorder(node.folder.id, allTaskIds)
    },
    [itemKeys, items, node.folder.id, onReorder],
  )

  return (
    <div style={{ paddingLeft: depth > 0 ? 16 : 0 }}>
      <FolderGroupHeader
        folderId={node.folder.id}
        folderName={node.folder.name}
        taskCount={totalCount}
        isExpanded={isExpanded}
        onToggle={() => onToggle(node.folder.id)}
        depth={depth}
      />

      {isExpanded && (
        <div className="pl-2 space-y-2 mt-2">
          {node.children.map((child) => (
            <FolderGroupContent
              key={child.folder.id}
              node={child}
              depth={depth + 1}
              expanded={expanded}
              onToggle={onToggle}
              onReorder={onReorder}
            />
          ))}

          {items.length > 0 && (
            <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
              <SortableContext items={itemKeys} strategy={verticalListSortingStrategy}>
                {items.map((item) => (
                  <SortableTaskItem key={item.key} item={item} />
                ))}
              </SortableContext>
            </DndContext>
          )}

          {items.length === 0 && node.children.length === 0 && (
            <p className="pl-8 text-sm text-muted dark:text-muted-dark py-2">此資料夾尚無任務</p>
          )}
        </div>
      )}
    </div>
  )
}

function countDescendantTasks(node: FolderNode): number {
  let count = node.tasks.length
  for (const child of node.children) {
    count += countDescendantTasks(child)
  }
  return count
}

// ---------------------------------------------------------------------------
// Main TaskList
// ---------------------------------------------------------------------------
export function TaskList() {
  const { data: taskData, isLoading: tasksLoading, isError: tasksError } = useTasks()
  const { data: folders = [] } = useFolders()
  useTaskNotifications(taskData)

  const createFolder = useCreateFolder()
  const reorderTasks = useReorderTasks()
  const deleteAllFailed = useDeleteAllFailedTasks()
  const [showNewFolder, setShowNewFolder] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')
  const [expanded, setExpanded] = useState<Record<string, boolean>>(loadExpanded)

  const toggleFolder = useCallback((key: string) => {
    setExpanded((prev) => {
      const next = { ...prev, [key]: !(prev[key] ?? true) }
      saveExpanded(next)
      return next
    })
  }, [])

  const handleCreateFolder = () => {
    const name = newFolderName.trim()
    if (!name) return
    createFolder.mutate({ name }, {
      onSuccess: () => { setNewFolderName(''); setShowNewFolder(false) },
    })
  }

  const handleReorder = useCallback(
    (folderId: string, taskIds: string[]) => {
      reorderTasks.mutate({ folderId, taskIds })
    },
    [reorderTasks],
  )

  const { folderTree, uncategorizedItems } = useMemo(() => {
    if (!taskData) return { folderTree: [], uncategorizedItems: [] as GroupedItem[] }

    const all = Object.values(taskData)
    const folderIdSet = new Set(folders.map((f) => f.id))
    const tasksByFolder = new Map<string, Task[]>()
    const uncategorized: Task[] = []

    for (const t of all) {
      if (t.folder_id && folderIdSet.has(t.folder_id)) {
        const list = tasksByFolder.get(t.folder_id) ?? []
        list.push(t)
        tasksByFolder.set(t.folder_id, list)
      } else {
        uncategorized.push(t)
      }
    }

    return {
      folderTree: buildFolderTree(folders, tasksByFolder),
      uncategorizedItems: buildGroupedItems(uncategorized),
    }
  }, [taskData, folders])

  const uncatItemKeys = useMemo(() => uncategorizedItems.map((i) => i.key), [uncategorizedItems])

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  const handleUncatDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event
      if (!over || active.id === over.id) return
      const oldIndex = uncatItemKeys.indexOf(active.id as string)
      const newIndex = uncatItemKeys.indexOf(over.id as string)
      if (oldIndex === -1 || newIndex === -1) return
      const reordered = [...uncatItemKeys]
      reordered.splice(oldIndex, 1)
      reordered.splice(newIndex, 0, active.id as string)

      const allTaskIds: string[] = []
      for (const key of reordered) {
        const item = uncategorizedItems.find((i) => i.key === key)
        if (item) allTaskIds.push(...item.taskIds)
      }
      handleReorder('_uncategorized', allTaskIds)
    },
    [uncatItemKeys, uncategorizedItems, handleReorder],
  )

  const totalTasks = taskData ? Object.keys(taskData).length : 0
  const failedCount = taskData
    ? Object.values(taskData).filter((t) => t.status === 'failed').length
    : 0

  if (tasksLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-24 w-full rounded-lg" />
        ))}
      </div>
    )
  }

  if (tasksError) {
    return <p className="text-center text-danger py-8">無法載入任務列表</p>
  }

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center gap-2">
        {showNewFolder ? (
          <div className="flex items-center gap-2 flex-1">
            <Input
              autoFocus
              placeholder="資料夾名稱"
              className="flex-1 h-8 text-sm"
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleCreateFolder()
                if (e.key === 'Escape') { setShowNewFolder(false); setNewFolderName('') }
              }}
            />
            <Button size="sm" onClick={handleCreateFolder} loading={createFolder.isPending}>
              建立
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => { setShowNewFolder(false); setNewFolderName('') }}
            >
              取消
            </Button>
          </div>
        ) : (
          <>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setShowNewFolder(true)}
            >
              <FolderPlus className="h-4 w-4" />
              新增資料夾
            </Button>
            {failedCount > 0 && (
              <Button
                size="sm"
                variant="outline"
                className="text-danger border-danger/40 hover:bg-danger/10"
                loading={deleteAllFailed.isPending}
                onClick={() => {
                  if (globalThis.confirm(`確定要刪除所有 ${failedCount} 個失敗任務嗎？`)) {
                    deleteAllFailed.mutate()
                  }
                }}
              >
                <Trash2 className="h-4 w-4" />
                刪除失敗任務 ({failedCount})
              </Button>
            )}
          </>
        )}
      </div>

      {/* Content */}
      {totalTasks === 0 && folders.length === 0 ? (
        <div className="text-center py-12">
          <Inbox className="h-12 w-12 mx-auto text-muted/40 dark:text-muted-dark/40 mb-3" />
          <p className="text-muted dark:text-muted-dark font-medium">尚無任務</p>
          <p className="text-sm text-muted/70 dark:text-muted-dark/70 mt-1">
            提交 URL、上傳檔案或匯入資料夾以開始轉錄
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {folderTree.map((node) => (
            <FolderGroupContent
              key={node.folder.id}
              node={node}
              depth={0}
              expanded={expanded}
              onToggle={toggleFolder}
              onReorder={handleReorder}
            />
          ))}

          {uncategorizedItems.length > 0 && (
            <div>
              <FolderGroupHeader
                folderId={null}
                folderName="未分類"
                taskCount={uncategorizedItems.length}
                isExpanded={expanded._uncategorized ?? true}
                onToggle={() => toggleFolder('_uncategorized')}
              />
              {(expanded._uncategorized ?? true) && (
                <div className="pl-2 space-y-2 mt-2">
                  <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleUncatDragEnd}>
                    <SortableContext items={uncatItemKeys} strategy={verticalListSortingStrategy}>
                      {uncategorizedItems.map((item) => (
                        <SortableTaskItem key={item.key} item={item} />
                      ))}
                    </SortableContext>
                  </DndContext>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
