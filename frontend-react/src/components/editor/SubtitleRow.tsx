import { useState, useRef, useEffect } from 'react'
import { useEditorStore } from '@/stores/editor-store'
import { formatTimestamp, cn } from '@/lib/utils'
import type { Subtitle } from '@/types/api'

interface SubtitleRowProps {
  subtitle: Subtitle
  index: number
  isActive: boolean
  onSelect: () => void
  onSeek: (time: number) => void
}

export function SubtitleRow({ subtitle, index, isActive, onSelect, onSeek }: SubtitleRowProps) {
  const updateSubtitle = useEditorStore((s) => s.updateSubtitle)
  const [editing, setEditing] = useState(false)
  const [editText, setEditText] = useState(subtitle.text)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus()
      inputRef.current.select()
    }
  }, [editing])

  const commit = () => {
    const trimmed = editText.trim()
    if (trimmed && trimmed !== subtitle.text) {
      updateSubtitle(index, { text: trimmed })
    } else {
      setEditText(subtitle.text)
    }
    setEditing(false)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); commit() }
    if (e.key === 'Escape') { setEditText(subtitle.text); setEditing(false) }
  }

  return (
    <div
      className={cn(
        'group flex gap-3 px-4 py-2.5 border-b border-border/50 dark:border-border-dark/50 transition-colors cursor-pointer',
        isActive ? 'bg-primary/10 dark:bg-primary/10 border-l-2 border-l-primary' : 'hover:bg-gray-50 dark:hover:bg-gray-800/50 border-l-2 border-l-transparent'
      )}
      onClick={onSelect}
    >
      <div className="shrink-0 w-16 text-right">
        <button
          type="button"
          className="text-xs font-mono text-primary/80 hover:text-primary cursor-pointer"
          onClick={(e) => { e.stopPropagation(); onSeek(subtitle.start_time) }}
          title="跳轉到此時間"
        >
          {formatTimestamp(subtitle.start_time)}
        </button>
        <p className="text-xs font-mono text-muted dark:text-muted-dark mt-0.5">
          {formatTimestamp(subtitle.end_time)}
        </p>
      </div>

      <div className="flex-1 min-w-0">
        {editing ? (
          <textarea
            ref={inputRef}
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
            onBlur={commit}
            onKeyDown={handleKeyDown}
            className="w-full resize-none rounded border border-primary bg-surface dark:bg-surface-dark px-2 py-1 text-sm text-text dark:text-text-dark focus:outline-none focus:ring-1 focus:ring-primary"
            rows={2}
          />
        ) : (
          <p
            className="text-sm text-text dark:text-text-dark leading-relaxed"
            onDoubleClick={() => { setEditText(subtitle.text); setEditing(true) }}
          >
            {subtitle.speaker && (
              <span className="font-medium text-primary mr-1">[{subtitle.speaker}]</span>
            )}
            {subtitle.text}
          </p>
        )}
      </div>

      <span className="shrink-0 text-xs font-mono text-muted/60 dark:text-muted-dark/60 tabular-nums self-center">
        #{subtitle.index + 1}
      </span>
    </div>
  )
}
