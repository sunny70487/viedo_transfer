import { memo } from 'react'
import { FileText, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { NoteRenderer } from './NoteRenderer'
import { ChapterScope, ImportanceBadge } from './ChapterPicker'
import type { NoteChapterState } from '@/types/api'

export interface ChapterRuntime {
  status: 'queued' | 'generating' | 'failed' | null
  streamed: string
  error: string
  /** Markdown saved during this session; null = use what the server returned. */
  markdown: string | null
  /** Generated in this session, so its concept animations are drawn automatically. */
  fresh: boolean
}

interface ChapterNoteSectionProps {
  taskId: string
  chapter: NoteChapterState
  runtime: ChapterRuntime | undefined
  canGenerate: boolean
  onGenerate: (chapterId: string) => void
}

const STATUS_LABEL = { queued: '等待中', generating: '產生中…', failed: '產生失敗' } as const

export const ChapterNoteSection = memo(function ChapterNoteSection({
  taskId, chapter, runtime, canGenerate, onGenerate,
}: Readonly<ChapterNoteSectionProps>) {
  const status = runtime?.status ?? null
  const generating = status === 'generating'
  const waiting = status === 'queued' || generating
  const saved = runtime?.markdown ?? chapter.markdown
  const body = generating ? runtime?.streamed ?? '' : saved ?? ''
  const error = status === 'failed' && (
    <p role="alert" className="text-sm text-danger">產生失敗：{runtime?.error || '未知原因'}</p>
  )

  if (!body) {
    return (
      <section
        aria-label={chapter.title}
        className="my-3 rounded-lg border border-dashed border-border dark:border-border-dark p-3"
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <h3 className="break-words text-sm font-medium text-text dark:text-text-dark">{chapter.title}</h3>
              <ImportanceBadge importance={chapter.importance} />
              <ChapterScope chapter={chapter} />
            </div>
            {chapter.summary && (
              <p className="mt-0.5 break-words text-sm text-muted dark:text-muted-dark">{chapter.summary}</p>
            )}
          </div>
          {waiting ? (
            <span className="shrink-0 animate-pulse text-sm text-muted dark:text-muted-dark" aria-live="polite">
              {STATUS_LABEL[status]}
            </span>
          ) : (
            <Button variant="outline" size="sm" className="shrink-0" disabled={!canGenerate} onClick={() => onGenerate(chapter.id)}>
              {status === 'failed'
                ? <RefreshCw className="h-4 w-4" aria-hidden="true" />
                : <FileText className="h-4 w-4" aria-hidden="true" />}
              {status === 'failed' ? '重試' : '產生'}
            </Button>
          )}
        </div>
        {error && <div className="mt-2">{error}</div>}
        {!waiting && status !== 'failed' && (
          <p className="mt-1 text-xs text-muted dark:text-muted-dark">尚未產生</p>
        )}
      </section>
    )
  }

  return (
    <section aria-label={chapter.title} className="relative">
      <div className="flex min-h-8 items-center justify-end gap-2 pt-1">
        {waiting ? (
          <span className="animate-pulse text-xs text-muted dark:text-muted-dark" aria-live="polite">
            {STATUS_LABEL[status]}
          </span>
        ) : (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs text-muted dark:text-muted-dark"
            disabled={!canGenerate}
            onClick={() => onGenerate(chapter.id)}
            aria-label={`重新產生章節：${chapter.title}`}
          >
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            {status === 'failed' ? '重試' : '重新產生'}
          </Button>
        )}
      </div>
      {error}
      <NoteRenderer
        markdown={body}
        streaming={generating}
        taskId={taskId}
        autoGenerateAnims={runtime?.fresh ?? false}
      />
      {generating && <span className="inline-block w-2 h-4 bg-primary/70 animate-pulse align-middle ml-0.5" />}
    </section>
  )
})
