const BIAS_STORAGE_KEY = 'whisper_asr_bias'

export interface BiasSettings {
  hotwords: string
  context: string
}

export function loadBiasSettings(): BiasSettings {
  try {
    const raw = localStorage.getItem(BIAS_STORAGE_KEY)
    if (raw) return JSON.parse(raw) as BiasSettings
  } catch { /* ignore */ }
  return { hotwords: '', context: '' }
}

export function saveBiasSettings(s: BiasSettings) {
  try {
    localStorage.setItem(BIAS_STORAGE_KEY, JSON.stringify(s))
  } catch { /* ignore */ }
}
