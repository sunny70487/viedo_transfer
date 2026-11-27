import { useEffect, useRef } from 'react'
import { Badge } from '@/components/ui/Badge'
import { cn, formatTimestamp } from '@/lib/utils'
import type { NoteChapter, NoteImportance } from '@/types/api'
import {
  allSections, chapterMinutes, defaultSelection, selectedCount, type SectionSelection,
} from './chapter-selection'

const IMPORTANCE: Record<NoteImportance, { label: string; variant: 'primary' | 'info' | 'default' }> = {
  core: { label: '核心', variant: 'primary' },
  supplementary: { label: '補充', variant: 'info' },
  optional: { label: '可略過', variant: 'default' },
}

const CHECKBOX_CLASS = 'h-4 w-4 shrink-0 cursor-pointer accent-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50'

export function ImportanceBadge({ importance }: Readonly<{ importance: NoteImportance }>) {
  const { label, variant } = IMPORTANCE[importance] ?? IMPORTANCE.supplementary
  return <Badge variant={variant} className="shrink-0">{label}</Badge>
}

/** How much of the recording a chapter draws on: "3 個小節 · 約 25 分鐘". */
export function ChapterScope({ chapter, selected }: Readonly<{ chapter: NoteChapter; selected?: SectionSelection }>) {
  const total = chapter.sections.length
  const used = selected
    ? selectedCount(chapter, selected)
    : chapter.sections.filter((section) => !section.excluded).length
  return (
    <span className="text-xs tabular-nums text-muted dark:text-muted-dark">
      {used === total ? `${total} 個小節` : `${used} / ${total} 個小節`}
      {used > 0 && ` · 約 ${chapterMinutes(chapter, selected)} 分鐘`}
    </span>
  )
}

function ChapterCheckbox({ state, label, onToggle }: Readonly<{
  state: 'all' | 'some' | 'none'
  label: string
  onToggle: () => void
}>) {
  const ref = useRef<HTMLInputElement>(null)
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = state === 'some'
  }, [state])
  return (
    <input
      ref={ref}
      type="checkbox"
      className={cn(CHECKBOX_CLASS, 'mt-0.5')}
      aria-label={label}
      checked={state === 'all'}
      onChange={onToggle}
    />
  )
}

interface ChapterPickerProps {
  chapters: NoteChapter[]
  selected: SectionSelection
  onChange: (next: Set<string>) => void
  disabled?: boolean
}

export function ChapterPicker({ chapters, selected, onChange, disabled }: Readonly<ChapterPickerProps>) {
  const chosenChapters = chapters.filter((chapter) => selectedCount(chapter, selected) > 0).length
  const linkClass = 'rounded text-sm text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer'

  const toggleSection = (id: string) => {
    const next = new Set(selected)
    if (!next.delete(id)) next.add(id)
    onChange(next)
  }

  const toggleChapter = (chapter: NoteChapter) => {
    const next = new Set(selected)
    const turnOn = selectedCount(chapter, selected) < chapter.sections.length
    chapter.sections.forEach((section) => {
      if (turnOn) next.add(section.id)
      else next.delete(section.id)
    })
    onChange(next)
  }

  return (
    <fieldset disabled={disabled} className="min-w-0">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <legend className="float-left text-sm font-medium text-text dark:text-text-dark">
          預計產生的章節
          <span className="ml-2 font-normal text-muted dark:text-muted-dark">
            已選 {chosenChapters} / {chapters.length} 章
          </span>
        </legend>
        <div className="flex gap-3">
          <button type="button" className={linkClass} onClick={() => onChange(defaultSelection(chapters))}>
            預設
          </button>
          <button type="button" className={linkClass} onClick={() => onChange(allSections(chapters))}>
            全選
          </button>
          <button type="button" className={linkClass} onClick={() => onChange(new Set())}>
            全不選
          </button>
        </div>
      </div>

      <ul className="max-h-[46vh] divide-y divide-border dark:divide-border-dark overflow-y-auto rounded-lg border border-border dark:border-border-dark">
        {chapters.map((chapter) => {
          const count = selectedCount(chapter, selected)
          const state = count === 0 ? 'none' : count === chapter.sections.length ? 'all' : 'some'
          const single = chapter.sections.length === 1
          return (
            <li key={chapter.id} className={cn(chapter.kind === 'logistics' && 'bg-gray-50 dark:bg-gray-800/40')}>
              <div className="flex items-start gap-3 px-3 py-2.5">
                <ChapterCheckbox state={state} label={`章節：${chapter.title}`} onToggle={() => toggleChapter(chapter)} />
                <div className={cn('min-w-0 flex-1', state === 'none' && 'opacity-60')}>
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="break-words text-sm font-medium text-text dark:text-text-dark">{chapter.title}</span>
                    <ImportanceBadge importance={chapter.importance} />
                    {single ? (
                      <span className="text-xs tabular-nums text-muted dark:text-muted-dark">
                        {formatTimestamp(chapter.sections[0].start)} – {formatTimestamp(chapter.sections[0].end)}
                      </span>
                    ) : (
                      <ChapterScope chapter={chapter} selected={selected} />
                    )}
                  </div>
                  {chapter.summary && (
                    <p className="mt-0.5 break-words text-sm text-muted dark:text-muted-dark">{chapter.summary}</p>
                  )}
                </div>
              </div>

              {!single && (
                <ul className="pb-2 pl-10 pr-3">
                  {chapter.sections.map((section) => {
                    const checked = selected.has(section.id)
                    return (
                      <li key={section.id}>
                        <label className="flex cursor-pointer items-start gap-2 rounded-md px-2 py-1 transition-colors duration-200 hover:bg-gray-100 dark:hover:bg-gray-800/60">
                          <input
                            type="checkbox"
                            className={cn(CHECKBOX_CLASS, 'mt-0.5 h-3.5 w-3.5')}
                            checked={checked}
                            onChange={() => toggleSection(section.id)}
                          />
                          <span className={cn('min-w-0 flex-1 text-sm', !checked && 'opacity-60')}>
                            <span className="mr-2 text-xs tabular-nums text-muted dark:text-muted-dark">
                              {formatTimestamp(section.start)} – {formatTimestamp(section.end)}
                            </span>
                            <span className="break-words text-text dark:text-text-dark">{section.title}</span>
                            {section.importance !== chapter.importance && (
                              <span className="ml-2 text-xs text-muted dark:text-muted-dark">
                                {IMPORTANCE[section.importance]?.label}
                              </span>
                            )}
                            {section.summary && (
                              <span className="block break-words text-xs text-muted dark:text-muted-dark">{section.summary}</span>
                            )}
                          </span>
                        </label>
                      </li>
                    )
                  })}
                </ul>
              )}
            </li>
          )
        })}
      </ul>
    </fieldset>
  )
}
