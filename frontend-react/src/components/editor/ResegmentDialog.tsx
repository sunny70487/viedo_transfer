import { useEffect, useState } from 'react'
import { Scissors } from 'lucide-react'
import { Dialog } from '@/components/ui/Dialog'
import { Button } from '@/components/ui/Button'
import { api } from '@/api/client'
import { toast } from '@/stores/toast-store'
import { loadBiasSettings, saveBiasSettings } from '@/lib/asr-bias'
import type { Subtitle } from '@/types/api'

interface ResegmentDialogProps {
  open: boolean
  onClose: () => void
  taskId: string
  onResegmented: (subs: Subtitle[]) => void
}

export function ResegmentDialog({
  open, onClose, taskId, onResegmented,
}: Readonly<ResegmentDialogProps>) {
  const [glossary, setGlossary] = useState('')
  const [running, setRunning] = useState(false)

  useEffect(() => {
    if (open) setGlossary(loadBiasSettings().hotwords)
  }, [open])

  const handleRun = async () => {
    setRunning(true)
    try {
      saveBiasSettings({ ...loadBiasSettings(), hotwords: glossary })
      const { subtitles } = await api.resegmentSubtitles(taskId, glossary)
      onResegmented(subtitles)
      toast('success', `已重新產生 ${subtitles.length} 行字幕，確認後請按「儲存」`)
      onClose()
    } catch (e) {
      toast('error', `重新產生失敗：${(e as Error).message}`)
    } finally {
      setRunning(false)
    }
  }

  return (
    <Dialog open={open} onClose={running ? () => {} : onClose} title="重新產生字幕">
      <div className="space-y-4">
        <p className="text-sm text-muted dark:text-muted-dark">
          不重跑語音辨識：沿用原始轉錄的字級時間，以最新的斷句規則和下方術語表重新排列字幕。
          目前編輯器的內容會被取代（包含手動修改），可用 Ctrl+Z 復原；按「儲存」前不會寫入檔案。
        </p>
        <div>
          <label
            htmlFor="resegment-glossary"
            className="block text-sm font-medium text-text dark:text-text-dark mb-1"
          >
            專有名詞 / 術語 <span className="text-muted dark:text-muted-dark font-normal">（選填）</span>
          </label>
          <textarea
            id="resegment-glossary"
            className="w-full rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark px-3 py-2 text-sm text-text dark:text-text-dark placeholder:text-muted/60 focus:outline-none focus:ring-2 focus:ring-primary/40 resize-y min-h-[96px] font-mono"
            rows={5}
            placeholder={'一行一個，或用逗號分隔\n線程環境塊\nOlly Debugger=>OllyDbg'}
            value={glossary}
            onChange={(e) => setGlossary(e.target.value)}
            disabled={running}
          />
          <p className="text-xs text-muted dark:text-muted-dark mt-1">
            術語不會被拆到兩行；同音字會修正成術語；「錯字=&gt;正確」直接替換。與轉錄設定的術語欄位共用。
          </p>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" size="sm" onClick={onClose} disabled={running}>
            取消
          </Button>
          <Button size="sm" onClick={handleRun} loading={running}>
            <Scissors className="h-4 w-4" />
            重新產生
          </Button>
        </div>
      </div>
    </Dialog>
  )
}
