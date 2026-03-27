import type {
  Task, GpuInfo, DirectoryInfo, SubdirectoryItem,
  SubtitleCollection, TranscriptionRequest,
  RetranscribeRequest, RetranscribeTask,
  BatchResponse,
} from '@/types/api'

const BASE = ''

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || body.error || `Request failed: ${res.status}`)
  }
  return res.json()
}

export const api = {
  transcribeUrl(data: TranscriptionRequest) {
    return request<{ task_id: string }>('/transcribe/url', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  },

  transcribeUpload(file: File, params: Record<string, string>) {
    const form = new FormData()
    form.append('file', file)
    Object.entries(params).forEach(([k, v]) => form.append(k, v))
    return fetch(`${BASE}/transcribe/upload`, { method: 'POST', body: form })
      .then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => ({}))
          throw new Error(body.detail || 'Upload failed')
        }
        return res.json() as Promise<{ task_id: string }>
      })
  },

  transcribeBatchUrls(data: { urls: string[] } & Record<string, unknown>) {
    return request<BatchResponse>('/transcribe/batch/urls', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  },

  transcribeBatchUpload(files: File[], params: Record<string, string>) {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    Object.entries(params).forEach(([k, v]) => form.append(k, v))
    return fetch(`${BASE}/transcribe/batch/upload`, { method: 'POST', body: form })
      .then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => ({}))
          throw new Error(body.detail || 'Batch upload failed')
        }
        return res.json() as Promise<BatchResponse>
      })
  },

  getTasks() {
    return request<Record<string, Task>>('/tasks')
  },

  getTask(taskId: string) {
    return request<Task>(`/tasks/${taskId}`)
  },

  deleteTask(taskId: string) {
    return request<{ message: string }>(`/tasks/${taskId}`, { method: 'DELETE' })
  },

  getGpuInfo() {
    return request<GpuInfo>('/gpu-info')
  },

  getDirectories() {
    return request<DirectoryInfo>('/system/directories')
  },

  getSubdirectories(dirPath: string) {
    return request<{ path: string; subdirectories: SubdirectoryItem[] }>(
      `/system/subdirectories?path=${encodeURIComponent(dirPath)}`
    )
  },

  getSubtitles(taskId: string, includeWords = true) {
    return request<SubtitleCollection>(
      `/api/subtitles/${taskId}?include_words=${includeWords}`
    )
  },

  saveSubtitles(taskId: string, data: SubtitleCollection) {
    return request<{ message: string; updated_at: string; total_segments: number }>(
      `/api/subtitles/${taskId}`, { method: 'PUT', body: JSON.stringify(data) }
    )
  },

  async checkSubtitlesExist(taskId: string): Promise<boolean> {
    const res = await fetch(`${BASE}/api/subtitles/${taskId}`, { method: 'HEAD' })
    return res.ok
  },

  downloadSubtitle(taskId: string, format: string, encoding = 'utf-8') {
    return `${BASE}/api/subtitles/${taskId}/download/${format}?encoding=${encoding}`
  },

  downloadFile(taskId: string, fileType: string) {
    return `${BASE}/download/${taskId}/${fileType}`
  },

  retranscribe(taskId: string, data: RetranscribeRequest) {
    return request<{ retranscribe_task_id: string; message: string; status: string }>(
      `/api/subtitles/${taskId}/retranscribe`, { method: 'POST', body: JSON.stringify(data) }
    )
  },

  getRetranscribeTask(retranscribeTaskId: string) {
    return request<RetranscribeTask>(`/api/subtitles/retranscribe/${retranscribeTaskId}`)
  },

  applyRetranscribe(taskId: string, retranscribeTaskId: string) {
    return request<{ message: string; subtitle_index: number; updated_text: string }>(
      `/api/subtitles/${taskId}/retranscribe/${retranscribeTaskId}/apply`, { method: 'POST' }
    )
  },
}
