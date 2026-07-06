const LLM_STORAGE_KEY = 'whisper_llm_settings'

export interface LlmSettings {
  api_key: string
  base_url: string
  model: string
  content_hint: string
}

const DEFAULTS: LlmSettings = {
  api_key: '',
  base_url: 'https://api.openai.com/v1',
  model: 'gpt-4o-mini',
  content_hint: '',
}

export function loadLlmSettings(): LlmSettings {
  try {
    const raw = localStorage.getItem(LLM_STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      return {
        api_key: parsed.llm_api_key || '',
        base_url: parsed.llm_base_url || DEFAULTS.base_url,
        model: parsed.llm_model || DEFAULTS.model,
        content_hint: parsed.llm_content_hint || '',
      }
    }
  } catch { /* ignore */ }
  return { ...DEFAULTS }
}

export function saveLlmSettings(s: Partial<LlmSettings>) {
  try {
    const current = loadLlmSettings()
    const merged = { ...current, ...s }
    localStorage.setItem(LLM_STORAGE_KEY, JSON.stringify({
      llm_api_key: merged.api_key,
      llm_base_url: merged.base_url,
      llm_model: merged.model,
      llm_content_hint: merged.content_hint,
    }))
  } catch { /* ignore */ }
}
