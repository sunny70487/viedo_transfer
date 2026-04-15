import { useMemo } from 'react'
import { FolderOpen } from 'lucide-react'
import { useFolders } from '@/hooks/use-folders'
import type { Folder } from '@/types/api'

interface FolderSelectProps {
  value: string
  onChange: (folderId: string) => void
}

function buildFolderTree(folders: Folder[]): { folder: Folder; depth: number }[] {
  const childrenMap = new Map<string | null, Folder[]>()
  for (const f of folders) {
    const key = f.parent_id ?? null
    const list = childrenMap.get(key) ?? []
    list.push(f)
    childrenMap.set(key, list)
  }

  const result: { folder: Folder; depth: number }[] = []
  function walk(parentId: string | null, depth: number) {
    const children = childrenMap.get(parentId) ?? []
    for (const c of children) {
      result.push({ folder: c, depth })
      walk(c.id, depth + 1)
    }
  }
  walk(null, 0)
  return result
}

export function FolderSelect({ value, onChange }: Readonly<FolderSelectProps>) {
  const { data: folders = [] } = useFolders()
  const tree = useMemo(() => buildFolderTree(folders), [folders])

  if (folders.length === 0) return null

  return (
    <div>
      <label htmlFor="folder-select" className="block text-sm font-medium text-text dark:text-text-dark mb-1.5">
        目標資料夾
      </label>
      <div className="relative">
        <FolderOpen className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted pointer-events-none" />
        <select
          id="folder-select"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full pl-10 pr-3 py-2 text-sm rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark text-text dark:text-text-dark focus:outline-none focus:ring-2 focus:ring-primary/40 appearance-none cursor-pointer"
        >
          <option value="">未分類</option>
          {tree.map(({ folder, depth }) => (
            <option key={folder.id} value={folder.id}>
              {'　'.repeat(depth)}{depth > 0 ? '└ ' : ''}{folder.name}
            </option>
          ))}
        </select>
      </div>
    </div>
  )
}
