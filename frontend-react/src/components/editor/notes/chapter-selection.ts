import type { NoteChapter } from '@/types/api'

/** Selection is a set of section ids; a chapter is written when any of its sections is selected. */
export type SectionSelection = ReadonlySet<string>

/** Every knowledge section; course admin and chit-chat stay unticked. */
export function defaultSelection(chapters: NoteChapter[]): Set<string> {
  return new Set(
    chapters
      .filter((chapter) => chapter.kind !== 'logistics')
      .flatMap((chapter) => chapter.sections.map((section) => section.id)),
  )
}

export function allSections(chapters: NoteChapter[]): Set<string> {
  return new Set(chapters.flatMap((chapter) => chapter.sections.map((section) => section.id)))
}

export function selectedCount(chapter: NoteChapter, selected: SectionSelection): number {
  return chapter.sections.filter((section) => selected.has(section.id)).length
}

export function chaptersToGenerate(chapters: NoteChapter[], selected: SectionSelection): string[] {
  return chapters
    .filter((chapter) => selectedCount(chapter, selected) > 0)
    .map((chapter) => chapter.id)
}

/**
 * Sections unticked inside chapters that will be written. Sections of a
 * chapter that is skipped entirely are not listed, so that chapter can still
 * be generated later with all of its content.
 */
export function excludedSections(chapters: NoteChapter[], selected: SectionSelection): string[] {
  return chapters
    .filter((chapter) => selectedCount(chapter, selected) > 0)
    .flatMap((chapter) => chapter.sections)
    .filter((section) => !selected.has(section.id))
    .map((section) => section.id)
}

/** Rounded minutes of the sections that count, at least 1. */
export function chapterMinutes(chapter: NoteChapter, selected?: SectionSelection): number {
  const seconds = chapter.sections
    .filter((section) => (selected ? selected.has(section.id) : !section.excluded))
    .reduce((total, section) => total + Math.max(0, section.end - section.start), 0)
  return Math.max(1, Math.round(seconds / 60))
}
