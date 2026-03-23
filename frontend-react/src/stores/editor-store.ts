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
