import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type ThemeMode = 'light' | 'dark' | 'system'

interface ThemeState {
  mode: ThemeMode
  resolved: 'light' | 'dark'
  setMode: (mode: ThemeMode) => void
}

function getSystemTheme(): 'light' | 'dark' {
  if (typeof window === 'undefined') return 'light'
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function applyTheme(resolved: 'light' | 'dark') {
  const root = document.documentElement
  root.classList.toggle('dark', resolved === 'dark')
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      mode: 'system',
      resolved: getSystemTheme(),
      setMode: (mode) => {
        const resolved = mode === 'system' ? getSystemTheme() : mode
        applyTheme(resolved)
        set({ mode, resolved })
      },
    }),
    {
      name: 'whisper-theme',
      onRehydrateStorage: () => (state) => {
        if (state) {
          const resolved = state.mode === 'system' ? getSystemTheme() : state.mode
          applyTheme(resolved)
          state.resolved = resolved
        }
      },
    }
  )
)

if (typeof window !== 'undefined') {
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    const { mode, setMode } = useThemeStore.getState()
    if (mode === 'system') setMode('system')
  })
}
