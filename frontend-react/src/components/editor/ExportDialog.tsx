import { useState } from 'react'
import { Download } from 'lucide-react'
import { Dialog } from '@/components/ui/Dialog'
import { Button } from '@/components/ui/Button'
import { EXPORT_FORMATS } from '@/lib/constants'
import { api } from '@/api/client'

interface ExportDialogProps {
  open: boolean
  onClose: () => void
  taskId: string
}

export function ExportDialog({ open, onClose, taskId }: ExportDialogProps) {
  const [encoding, setEncoding] = useState('utf-8')

  return (
    <Dialog open={open} onClose={onClose} title="匯出字幕">
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-text dark:text-text-dark mb-2">編碼</label>
          <select
            className="h-9 w-full rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark px-3 text-sm cursor-pointer"
            value={encoding}
            onChange={(e) => setEncoding(e.target.value)}
          >
            <option value="utf-8">UTF-8</option>
            <option value="utf-8-sig">UTF-8 BOM</option>
            <option value="big5">Big5</option>
            <option value="gb2312">GB2312</option>
          </select>
        </div>
        <div className="grid grid-cols-2 gap-2">
          {EXPORT_FORMATS.map((fmt) => (
            <a
              key={fmt.value}
              href={api.downloadSubtitle(taskId, fmt.value, encoding)}
              download
              className="flex items-center gap-2 px-4 py-3 rounded-lg border border-border dark:border-border-dark hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors cursor-pointer"
            >
              <Download className="h-4 w-4 text-primary" />
              <div>
                <p className="text-sm font-medium text-text dark:text-text-dark">{fmt.label}</p>
                <p className="text-xs text-muted dark:text-muted-dark">{fmt.description}</p>
              </div>
            </a>
          ))}
        </div>
        <div className="flex justify-end">
          <Button variant="outline" onClick={onClose}>關閉</Button>
        </div>
      </div>
    </Dialog>
  )
}
