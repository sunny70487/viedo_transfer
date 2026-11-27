import { useState } from 'react'
import { Link2, Plus, RefreshCw, X } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { api } from '@/api/client'
import { toast } from '@/stores/toast-store'
import { cn } from '@/lib/utils'
import type { NoteReferences } from '@/types/api'

const MAX_URLS = 5
const MAX_CHARS = 20_000
const MAX_TEXT_LENGTH = 200_000

interface ReferenceInputProps {
  taskId: string
  references: NoteReferences
  text: string
  onTextChange: (text: string) => void
  onChange: (next: NoteReferences) => void
  disabled?: boolean
}

export function ReferenceInput({
  taskId, references, text, onTextChange, onChange, disabled,
}: Readonly<ReferenceInputProps>) {
  const [url, setUrl] = useState('')
  const [urlError, setUrlError] = useState('')
  const [busy, setBusy] = useState(false)

  const urls = references.sources.map((s) => s.url)
  const locked = disabled || busy
  const atLimit = urls.length >= MAX_URLS

  const save = async (nextUrls: string[]): Promise<boolean> => {
    setBusy(true)
    try {
      onChange(await api.saveNoteReferences(taskId, { text, urls: nextUrls }))
      return true
    } catch (e) {
      toast('error', `參考資料儲存失敗: ${(e as Error).message}`)
      return false
    } finally {
      setBusy(false)
    }
  }

  const handleAdd = async () => {
    const next = url.trim()
    if (!/^https?:\/\/\S+$/i.test(next)) {
      setUrlError('請輸入以 http:// 或 https:// 開頭的網址')
      return
    }
    if (urls.includes(next)) {
      setUrlError('這個網址已經加入')
      return
    }
    setUrlError('')
    if (await save([...urls, next])) setUrl('')
  }

  // The backend caches failed URLs, so a retry has to drop the URL first.
  const handleRetry = async (target: string) => {
    if (await save(urls.filter((u) => u !== target))) await save(urls)
  }

  return (
    <div className="space-y-3">
      <div>
        <label htmlFor="notes-ref-text" className="mb-1 block text-sm font-medium text-text dark:text-text-dark">
          參考資料 <span className="font-normal text-muted dark:text-muted-dark">（選填）</span>
        </label>
        <p className="mb-1.5 text-xs text-muted dark:text-muted-dark">
          貼上講義、文件內容或加入網址。產生每個章節時都會帶上，只取與該章相關的部分來補充細節與修正專有名詞。
        </p>
        <textarea
          id="notes-ref-text"
          className="min-h-[72px] w-full resize-y rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark px-3 py-2 text-sm text-text dark:text-text-dark placeholder:text-muted/60 focus:outline-none focus:ring-2 focus:ring-primary/40 disabled:opacity-60"
          rows={3}
          maxLength={MAX_TEXT_LENGTH}
          placeholder="貼上要參考的文字"
          value={text}
          disabled={disabled}
          onChange={(e) => onTextChange(e.target.value)}
          onBlur={() => { if (text !== references.text) void save(urls) }}
        />
        <p className={cn('mt-0.5 text-xs', text.length > MAX_CHARS ? 'text-danger' : 'text-muted dark:text-muted-dark')}>
          {text.length.toLocaleString()} / {MAX_CHARS.toLocaleString()} 字
          {text.length > MAX_CHARS && `，只會使用前 ${MAX_CHARS.toLocaleString()} 字`}
        </p>
      </div>

      <div>
        <div className="flex gap-2">
          <Input
            type="url"
            inputMode="url"
            aria-label="參考網址"
            aria-invalid={Boolean(urlError)}
            aria-describedby="notes-ref-url-hint"
            className="h-9"
            placeholder="https://"
            value={url}
            disabled={locked || atLimit}
            onChange={(e) => { setUrl(e.target.value); setUrlError('') }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.nativeEvent.isComposing) {
                e.preventDefault()
                void handleAdd()
              }
            }}
          />
          <Button
            variant="outline"
            size="sm"
            className="h-9 shrink-0"
            onClick={() => void handleAdd()}
            loading={busy}
            disabled={disabled || atLimit || !url.trim()}
          >
            {!busy && <Plus className="h-4 w-4" aria-hidden="true" />}
            {busy ? '讀取中' : '加入'}
          </Button>
        </div>
        <p id="notes-ref-url-hint" className="mt-1 text-xs text-muted dark:text-muted-dark">
          {atLimit
            ? `最多 ${MAX_URLS} 個網址，請先移除一個再加入。`
            : '需要登入、以 JavaScript 載入內容的網頁與 PDF 讀不到，請改用貼上文字。'}
        </p>
        {urlError && <p role="alert" className="mt-1 text-xs text-danger">{urlError}</p>}
      </div>

      {references.sources.length > 0 && (
        <ul className="divide-y divide-border dark:divide-border-dark rounded-lg border border-border dark:border-border-dark">
          {references.sources.map((source) => (
            <li key={source.url} className="flex items-start gap-2 px-3 py-2">
              <Link2 className={cn('mt-0.5 h-4 w-4 shrink-0', source.ok ? 'text-muted dark:text-muted-dark' : 'text-danger')} aria-hidden="true" />
              <div className="min-w-0 flex-1 text-sm">
                <p className="truncate text-text dark:text-text-dark" title={source.url}>
                  {source.ok && source.title ? source.title : source.url}
                </p>
                {source.ok ? (
                  <p className="truncate text-xs text-muted dark:text-muted-dark">
                    {source.chars.toLocaleString()} 字
                    {source.links > 0 && ` · 連到 ${source.links} 個子頁`}
                    {source.title && ` · ${source.url}`}
                  </p>
                ) : (
                  <p role="alert" className="text-xs text-danger">讀取失敗：{source.error || '未知原因'}</p>
                )}
              </div>
              {!source.ok && (
                <Button variant="ghost" size="sm" className="h-7 shrink-0 px-2" disabled={locked} onClick={() => void handleRetry(source.url)}>
                  <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                  重試
                </Button>
              )}
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 shrink-0"
                disabled={locked}
                aria-label={`移除 ${source.title || source.url}`}
                title="移除"
                onClick={() => void save(urls.filter((u) => u !== source.url))}
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </Button>
            </li>
          ))}
        </ul>
      )}

      {references.used_chars > 0 && (
        <p className="text-xs text-muted dark:text-muted-dark">
          目前會使用 {references.used_chars.toLocaleString()} 字的參考資料
          {references.truncated && '（超過上限，已截斷）'}
        </p>
      )}
      {references.sources.some((source) => source.links > 0) && (
        <p className="text-xs text-muted dark:text-muted-dark">
          產生每一章時，會從這些子頁中挑最多 2 個與該章相關的來讀，只取相關段落，並在章末列出用了哪些頁面。
        </p>
      )}
    </div>
  )
}
