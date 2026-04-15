import { create } from 'zustand'
import type { Subtitle } from '@/types/api'

interface EditorState {
  subtitles: Subtitle[]
  originalSubtitles: Subtitle[]
  isDirty: boolean
  selectedIndex: number
  history: Subtitle[][]
  historyIndex: number
  searchTerm: string

  setSubtitles: (subs: Subtitle[]) => void
  updateSubtitle: (index: number, update: Partial<Subtitle>) => void
  bulkUpdateTexts: (texts: string[]) => void
  replaceSubtitles: (subs: Subtitle[]) => void
  splitSubtitle: (index: number, splitTime: number) => void
  mergeWithNext: (index: number) => void
  setSelectedIndex: (index: number) => void
  setSearchTerm: (term: string) => void
  undo: () => void
  redo: () => void
  resetToOriginal: () => void
  markSaved: () => void
}

const MAX_HISTORY = 50

export const useEditorStore = create<EditorState>()((set, get) => ({
  subtitles: [],
  originalSubtitles: [],
  isDirty: false,
  selectedIndex: -1,
  history: [],
  historyIndex: -1,
  searchTerm: '',

  setSubtitles: (subs) => {
    const copy = JSON.parse(JSON.stringify(subs))
    set({
      subtitles: copy,
      originalSubtitles: JSON.parse(JSON.stringify(subs)),
      isDirty: false,
      history: [copy],
      historyIndex: 0,
      selectedIndex: -1,
    })
  },

  updateSubtitle: (index, update) => {
    const { subtitles, history, historyIndex } = get()
    const next = subtitles.map((s, i) => i === index ? { ...s, ...update } : s)
    const newHistory = history.slice(0, historyIndex + 1)
    newHistory.push(JSON.parse(JSON.stringify(next)))
    if (newHistory.length > MAX_HISTORY) newHistory.shift()
    set({
      subtitles: next,
      isDirty: true,
      history: newHistory,
      historyIndex: newHistory.length - 1,
    })
  },

  bulkUpdateTexts: (texts) => {
    const { subtitles, history, historyIndex } = get()
    const next = subtitles.map((s, i) => ({ ...s, text: texts[i] ?? s.text }))
    const newHistory = history.slice(0, historyIndex + 1)
    newHistory.push(JSON.parse(JSON.stringify(next)))
    if (newHistory.length > MAX_HISTORY) newHistory.shift()
    set({
      subtitles: next,
      isDirty: true,
      history: newHistory,
      historyIndex: newHistory.length - 1,
    })
  },

  replaceSubtitles: (subs) => {
    const { history, historyIndex } = get()
    const next = JSON.parse(JSON.stringify(subs))
    const newHistory = history.slice(0, historyIndex + 1)
    newHistory.push(next)
    if (newHistory.length > MAX_HISTORY) newHistory.shift()
    set({
      subtitles: next,
      isDirty: true,
      history: newHistory,
      historyIndex: newHistory.length - 1,
    })
  },

  splitSubtitle: (index, splitTime) => {
    const { subtitles, history, historyIndex } = get()
    const sub = subtitles[index]
    if (!sub || splitTime <= sub.start_time || splitTime >= sub.end_time) return

    const ratio = (splitTime - sub.start_time) / (sub.end_time - sub.start_time)
    const splitChar = Math.round(sub.text.length * ratio)

    const first: Subtitle = { ...sub, end_time: splitTime, text: sub.text.slice(0, splitChar).trim() || sub.text }
    const second: Subtitle = { ...sub, index: sub.index + 1, start_time: splitTime, text: sub.text.slice(splitChar).trim() || '' }

    const next = [
      ...subtitles.slice(0, index),
      first,
      second,
      ...subtitles.slice(index + 1).map(s => ({ ...s, index: s.index + 1 })),
    ]

    const newHistory = history.slice(0, historyIndex + 1)
    newHistory.push(JSON.parse(JSON.stringify(next)))
    if (newHistory.length > MAX_HISTORY) newHistory.shift()
    set({ subtitles: next, isDirty: true, history: newHistory, historyIndex: newHistory.length - 1 })
  },

  mergeWithNext: (index) => {
    const { subtitles, history, historyIndex } = get()
    if (index < 0 || index >= subtitles.length - 1) return

    const current = subtitles[index]
    const nextSub = subtitles[index + 1]
    const merged: Subtitle = {
      ...current,
      end_time: nextSub.end_time,
      text: `${current.text} ${nextSub.text}`.trim(),
    }

    const next = [
      ...subtitles.slice(0, index),
      merged,
      ...subtitles.slice(index + 2).map(s => ({ ...s, index: s.index - 1 })),
    ]

    const newHistory = history.slice(0, historyIndex + 1)
    newHistory.push(JSON.parse(JSON.stringify(next)))
    if (newHistory.length > MAX_HISTORY) newHistory.shift()
    set({ subtitles: next, isDirty: true, history: newHistory, historyIndex: newHistory.length - 1 })
  },

  setSelectedIndex: (index) => set({ selectedIndex: index }),
  setSearchTerm: (term) => set({ searchTerm: term }),

  undo: () => {
    const { history, historyIndex } = get()
    if (historyIndex <= 0) return
    const prev = historyIndex - 1
    set({
      subtitles: JSON.parse(JSON.stringify(history[prev])),
      historyIndex: prev,
      isDirty: true,
    })
  },

  redo: () => {
    const { history, historyIndex } = get()
    if (historyIndex >= history.length - 1) return
    const next = historyIndex + 1
    set({
      subtitles: JSON.parse(JSON.stringify(history[next])),
      historyIndex: next,
      isDirty: true,
    })
  },

  resetToOriginal: () => {
    const { originalSubtitles } = get()
    const copy = JSON.parse(JSON.stringify(originalSubtitles))
    set({
      subtitles: copy,
      isDirty: false,
      history: [copy],
      historyIndex: 0,
    })
  },

  markSaved: () => set({ isDirty: false, originalSubtitles: JSON.parse(JSON.stringify(get().subtitles)) }),
}))
