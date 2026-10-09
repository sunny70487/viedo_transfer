import { useRef } from 'react'
import { Undo2, Redo2, Save, Download, Upload, Search, RotateCcw, Sparkles, FileText } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { useEditorStore } from '@/stores/editor-store'
import { parseSubtitleFile, IMPORTABLE_EXTENSIONS } from '@/lib/subtitle-parser'
import { toast } from '@/stores/toast-store'
import type { Subtitle } from '@/types/api'

interface SubtitleToolbarProps {
  onSave: () => void
  onExport: () => void
  onEnhance: () => void
  onGenerateNotes: () => void
  onImport: (subs: Subtitle[]) => void
  saving?: boolean
  disabled?: boolean
}

export function SubtitleToolbar({ onSave, onExport, onEnhance, onGenerateNotes, onImport, saving, disabled }: Readonly<SubtitleToolbarProps>) {
  const { isDirty, searchTerm, setSearchTerm, undo, redo, resetToOriginal, historyIndex, history } = useEditorStore()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const text = await file.text()
      const subs = parseSubtitleFile(text, file.name)
      if (subs.length === 0) {
        toast('error', '無法解析字幕檔案，請確認格式正確')
        return
      }
      onImport(subs)
      toast('success', `已匯入 ${subs.length} 行字幕 (${file.name})`)
    } catch {
      toast('error', '讀取字幕檔案失敗')
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

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
        <input
          ref={fileInputRef}
          type="file"
          accept={IMPORTABLE_EXTENSIONS}
          className="hidden"
          onChange={handleFileChange}
        />
        <Button variant="outline" size="sm" onClick={() => fileInputRef.current?.click()} disabled={disabled} title="匯入字幕檔 (SRT/VTT/ASS)">
          <Upload className="h-4 w-4" />
          匯入
        </Button>
        <Button variant="outline" size="sm" onClick={onEnhance} disabled={disabled} title="AI 字幕增強 / 翻譯">
          <Sparkles className="h-4 w-4" />
          AI 增強
        </Button>
        <Button variant="outline" size="sm" onClick={onGenerateNotes} disabled={disabled} title="依字幕產生圖文並茂的教學筆記">
          <FileText className="h-4 w-4" />
          產生筆記
        </Button>
        <Button variant="outline" size="sm" onClick={onExport} disabled={disabled}>
          <Download className="h-4 w-4" />
          匯出
        </Button>
        <Button size="sm" onClick={onSave} disabled={disabled || !isDirty} loading={saving}>
          <Save className="h-4 w-4" />
          儲存
        </Button>
      </div>
    </div>
  )
}
