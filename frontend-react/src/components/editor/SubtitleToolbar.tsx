import { Undo2, Redo2, Save, Download, Search, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { useEditorStore } from '@/stores/editor-store'

interface SubtitleToolbarProps {
  onSave: () => void
  onExport: () => void
  saving?: boolean
}

export function SubtitleToolbar({ onSave, onExport, saving }: SubtitleToolbarProps) {
  const { isDirty, searchTerm, setSearchTerm, undo, redo, resetToOriginal, historyIndex, history } = useEditorStore()

  return (
    <div className="flex flex-wrap items-center gap-2 px-4 py-3 border-b border-border dark:border-border-dark bg-surface dark:bg-surface-dark">
      <div className="flex items-center gap-1">
        <Button variant="ghost" size="icon" onClick={undo} disabled={historyIndex <= 0} title="復原 (Ctrl+Z)">
          <Undo2 className="h-4 w-4" />
        </Button>
        <Button variant="ghost" size="icon" onClick={redo} disabled={historyIndex >= history.length - 1} title="重做 (Ctrl+Y)">
          <Redo2 className="h-4 w-4" />
        </Button>
        <Button variant="ghost" size="icon" onClick={resetToOriginal} disabled={!isDirty} title="重置">
          <RotateCcw className="h-4 w-4" />
        </Button>
      </div>

      <div className="h-6 w-px bg-border dark:bg-border-dark" />

      <div className="relative flex-1 min-w-[180px] max-w-xs">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted" />
        <Input
          placeholder="搜尋字幕..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="pl-9 h-9"
        />
      </div>

      <div className="ml-auto flex items-center gap-2">
        <Button variant="outline" size="sm" onClick={onExport}>
          <Download className="h-4 w-4" />
          匯出
        </Button>
        <Button size="sm" onClick={onSave} disabled={!isDirty} loading={saving}>
          <Save className="h-4 w-4" />
          儲存
        </Button>
      </div>
    </div>
  )
}
