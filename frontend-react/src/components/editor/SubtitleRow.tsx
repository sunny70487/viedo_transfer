import { useState, useRef, useEffect } from 'react'
import { Scissors, Merge } from 'lucide-react'
import { useEditorStore } from '@/stores/editor-store'
import { formatTimestamp, cn } from '@/lib/utils'
import type { Subtitle } from '@/types/api'

interface SubtitleRowProps {
  subtitle: Subtitle
  index: number
  isActive: boolean
  onSelect: () => void
  onSeek: (time: number) => void
  onPause?: () => void
  currentTime?: number
}

export function SubtitleRow({ subtitle, index, isActive, onSelect, onSeek, onPause, currentTime }: Readonly<SubtitleRowProps>) {
  const updateSubtitle = useEditorStore((s) => s.updateSubtitle)
  const splitSubtitle = useEditorStore((s) => s.splitSubtitle)
  const mergeWithNext = useEditorStore((s) => s.mergeWithNext)
  const subtitlesCount = useEditorStore((s) => s.subtitles.length)
  const [editing, setEditing] = useState(false)
  const [editText, setEditText] = useState(subtitle.text)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const prevIdxRef = useRef(subtitle.index)

  if (prevIdxRef.current !== subtitle.index) {
    prevIdxRef.current = subtitle.index
    if (editing) setEditing(false)
    setEditText(subtitle.text)
  }

  useEffect(() => {
    if (!editing) setEditText(subtitle.text)
  }, [subtitle.text, editing])

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

  const canSplit = isActive && currentTime != null
    && currentTime > subtitle.start_time
    && currentTime < subtitle.end_time

  const canMerge = index < subtitlesCount - 1

  const handleSplit = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (canSplit && currentTime != null) {
      splitSubtitle(index, currentTime)
    }
  }

  const handleMerge = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (canMerge) {
      mergeWithNext(index)
    }
  }

  return (
    <div
      className={cn(
        'group flex gap-3 px-4 py-2.5 border-b border-border/50 dark:border-border-dark/50 transition-colors cursor-pointer',
        isActive ? 'bg-primary/10 dark:bg-primary/10 border-l-2 border-l-primary' : 'hover:bg-gray-50 dark:hover:bg-gray-800/50 border-l-2 border-l-transparent'
      )}
      onClick={() => {
        if (!editing) {
          onSelect()
          onSeek(subtitle.start_time)
        }
      }}
    >
      <div className="shrink-0 w-16 text-right">
        <span className="text-xs font-mono text-primary/80 hover:text-primary cursor-pointer">
          {formatTimestamp(subtitle.start_time)}
        </span>
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
            onDoubleClick={() => { setEditText(subtitle.text); setEditing(true); onPause?.() }}
          >
            {subtitle.speaker && (
              <span className="font-medium text-primary mr-1">[{subtitle.speaker}]</span>
            )}
            {subtitle.text}
          </p>
        )}
      </div>

      <div className="shrink-0 flex items-center gap-1">
        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            type="button"
            onClick={handleSplit}
            disabled={!canSplit}
            className={cn(
              'p-1 rounded transition-colors',
              canSplit
                ? 'text-amber-500 hover:bg-amber-500/10 hover:text-amber-400'
                : 'text-muted/30 dark:text-muted-dark/30 cursor-not-allowed'
            )}
            title="在當前播放時間分割 (Ctrl+D)"
          >
            <Scissors className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={handleMerge}
            disabled={!canMerge}
            className={cn(
              'p-1 rounded transition-colors',
              canMerge
                ? 'text-blue-500 hover:bg-blue-500/10 hover:text-blue-400'
                : 'text-muted/30 dark:text-muted-dark/30 cursor-not-allowed'
            )}
            title="與下一句合併 (Ctrl+M)"
          >
            <Merge className="h-3.5 w-3.5" />
          </button>
        </div>
        <span className="text-xs font-mono text-muted/60 dark:text-muted-dark/60 tabular-nums ml-1">
          #{subtitle.index + 1}
        </span>
      </div>
    </div>
  )
}
