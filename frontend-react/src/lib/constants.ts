export const MODEL_OPTIONS = [
  { value: 'qwen3-asr-1.7b', label: 'Qwen3-ASR 1.7B (推薦)', group: 'Qwen3-ASR' },
  { value: 'qwen3-asr-0.6b', label: 'Qwen3-ASR 0.6B (輕量)', group: 'Qwen3-ASR' },
  { value: 'paraformer-zh', label: 'Paraformer-zh', group: 'FunASR' },
  { value: 'sensevoice', label: 'SenseVoice', group: 'FunASR' },
  { value: 'large-v3', label: 'Whisper Large-v3', group: 'FunASR' },
  { value: 'large-v3-turbo', label: 'Whisper Large-v3 Turbo', group: 'FunASR' },
] as const

export const LANGUAGE_OPTIONS = [
  { value: '', label: '自動偵測' },
  { value: 'zh', label: '中文' },
  { value: 'en', label: '英文' },
  { value: 'ja', label: '日文' },
  { value: 'ko', label: '韓文' },
  { value: 'fr', label: '法文' },
  { value: 'de', label: '德文' },
  { value: 'es', label: '西班牙文' },
] as const

export const EXPORT_FORMATS = [
  { value: 'srt', label: 'SRT', description: 'SubRip 字幕格式' },
  { value: 'vtt', label: 'VTT', description: 'WebVTT 字幕格式' },
  { value: 'txt', label: 'TXT', description: '純文字' },
  { value: 'json', label: 'JSON', description: 'JSON 結構化資料' },
  { value: 'ass', label: 'ASS', description: 'Advanced SubStation Alpha' },
  { value: 'ssa', label: 'SSA', description: 'SubStation Alpha' },
] as const

export const TASK_STATUS = {
  queued: { label: '佇列中', color: 'bg-muted' },
  uploading: { label: '上傳中', color: 'bg-info' },
  downloading: { label: '下載中', color: 'bg-info' },
  processing: { label: '處理中', color: 'bg-primary' },
  transcribing: { label: '轉錄中', color: 'bg-primary' },
  completed: { label: '已完成', color: 'bg-success' },
  failed: { label: '失敗', color: 'bg-danger' },
} as const
