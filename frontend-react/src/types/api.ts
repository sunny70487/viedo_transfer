export interface Word {
  start: number
  end: number
  word: string
  confidence?: number
}

export interface Subtitle {
  index: number
  start_time: number
  end_time: number
  text: string
  words?: Word[]
  speaker?: string
  confidence?: number
}

export interface VideoInfo {
  duration?: number
  format?: string
  resolution?: string
  fps?: number
  video_url?: string
  file_size?: number
}

export interface SubtitleMetadata {
  language?: string
  model_used?: string
  created_at?: number
  last_modified?: number
  total_duration?: number
  total_segments?: number
  video_info?: VideoInfo
  transcription_settings?: Record<string, unknown>
}

export interface SubtitleCollection {
  task_id: string
  subtitles: Subtitle[]
  metadata: SubtitleMetadata
}

export interface TaskResult {
  files: Record<string, string>
  output_dir?: string
}

export interface PartialSegment {
  start: number
  end: number
  text: string
  speaker?: string
}

export interface Task {
  id: string
  status: string
  progress?: number
  message?: string
  result?: TaskResult
  error?: string
  start_time?: number
  end_time?: number
  source_name?: string
  batch_id?: string
  folder_id?: string
  sort_order?: number
  partial_segments?: PartialSegment[]
  source_file_path?: string
}

export interface SubtitleNotes {
  summary: string
  chapters: Array<{ time: number; title: string }>
}

export interface LlmSummarizeRequest {
  api_key: string
  base_url: string
  model: string
  content_hint?: string
}

export interface Folder {
  id: string
  name: string
  parent_id: string | null
  sort_order: number
  task_count: number
  created_at: number
  updated_at: number
}

export interface FolderUploadResponse {
  folder_id: string
  batch_id: string
  task_ids: string[]
  errors?: string[]
}

export interface BatchResponse {
  batch_id: string
  task_ids: string[]
  errors?: string[]
}

export interface GpuDevice {
  name: string
  memory_allocated: string
  memory_reserved: string
  max_memory: string
}

export interface GpuInfo {
  available: boolean
  device_count: number
  devices: GpuDevice[]
}

export interface DirectoryInfo {
  directories: string[]
  current: string
  system: string
}

export interface SubdirectoryItem {
  name: string
  path: string
  modified: number
}

export interface TranscriptionRequest {
  url?: string
  model_size?: string
  device?: string
  compute_type?: string
  language?: string
  task?: string
  beam_size?: number
  vad_filter?: boolean
  word_timestamps?: boolean
  output_format?: string
  split_segments?: boolean
  segment_duration?: number
  download_format?: string
  video_quality?: string
  output_dir?: string
  speaker_diarization?: boolean
  num_speakers?: number
  llm_enhance?: boolean
  llm_api_key?: string
  llm_base_url?: string
  llm_model?: string
  llm_content_hint?: string
}

export interface LlmModel {
  id: string
  name: string
}

export interface RetranscribeRequest {
  task_id: string
  start_time: number
  end_time: number
  subtitle_index: number
  model_settings?: Record<string, unknown>
}

export interface RetranscribeTask {
  id: string
  status: string
  progress?: number
  message?: string
  result?: {
    text: string
    segments: Subtitle[]
  }
  error?: string
}
