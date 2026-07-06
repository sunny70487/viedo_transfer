import type {
  Task, GpuInfo, DirectoryInfo, SubdirectoryItem,
  SubtitleCollection, TranscriptionRequest,
  RetranscribeRequest, RetranscribeTask,
  BatchResponse, LlmModel, Folder, FolderUploadResponse,
  SubtitleNotes, LlmSummarizeRequest,
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

  deleteAllFailedTasks() {
    return request<{ message: string; deleted_count: number }>('/tasks/failed', { method: 'DELETE' })
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

  downloadSubtitle(
    taskId: string,
    format: string,
    encoding = 'utf-8',
    swapBilingualLines = false
  ) {
    const q = new URLSearchParams({ encoding })
    if (swapBilingualLines) q.set('swap_bilingual_lines', 'true')
    return `${BASE}/api/subtitles/${taskId}/download/${format}?${q.toString()}`
  },

  downloadFile(taskId: string, fileType: string) {
    return `${BASE}/download/${taskId}/${fileType}`
  },

  downloadFolderSubtitles(folderId: string, format: string, encoding = 'utf-8') {
    const q = new URLSearchParams({ format, encoding })
    return `${BASE}/api/folders/${folderId}/download-subtitles?${q.toString()}`
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

  fetchLlmModels(apiKey: string, baseUrl: string) {
    return request<{ models: LlmModel[] }>('/api/llm/models', {
      method: 'POST',
      body: JSON.stringify({ api_key: apiKey, base_url: baseUrl }),
    })
  },

  // ---- Folder API ----

  getFolders() {
    return request<Folder[]>('/api/folders')
  },

  createFolder(name: string, parentId?: string | null) {
    return request<Folder>('/api/folders', {
      method: 'POST',
      body: JSON.stringify({ name, parent_id: parentId || null }),
    })
  },

  renameFolder(folderId: string, name: string) {
    return request<{ id: string; name: string }>(`/api/folders/${folderId}`, {
      method: 'PUT',
      body: JSON.stringify({ name }),
    })
  },

  deleteFolder(folderId: string) {
    return request<{ message: string }>(`/api/folders/${folderId}`, {
      method: 'DELETE',
    })
  },

  moveTasksToFolder(folderId: string, taskIds: string[]) {
    return request<{ message: string }>(`/api/folders/${folderId}/tasks`, {
      method: 'POST',
      body: JSON.stringify({ task_ids: taskIds }),
    })
  },

  removeTasksFromFolder(folderId: string, taskIds: string[]) {
    return request<{ message: string }>(`/api/folders/${folderId}/tasks`, {
      method: 'DELETE',
      body: JSON.stringify({ task_ids: taskIds }),
    })
  },

  reorderFolders(folderIds: string[]) {
    return request<{ message: string }>('/api/folders/reorder', {
      method: 'PUT',
      body: JSON.stringify({ folder_ids: folderIds }),
    })
  },

  reorderTasks(folderId: string, taskIds: string[]) {
    return request<{ message: string }>(`/api/folders/${folderId}/tasks/reorder`, {
      method: 'PUT',
      body: JSON.stringify({ task_ids: taskIds }),
    })
  },

  transcribeFolderUpload(
    files: File[],
    relativePaths: string[],
    folderName: string,
    params: Record<string, string>,
  ) {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    form.append('relative_paths', JSON.stringify(relativePaths))
    form.append('folder_name', folderName)
    Object.entries(params).forEach(([k, v]) => form.append(k, v))
    return fetch(`${BASE}/transcribe/batch/folder-upload`, { method: 'POST', body: form })
      .then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => ({}))
          throw new Error(body.detail || body.error || 'Folder upload failed')
        }
        return res.json() as Promise<FolderUploadResponse>
      })
  },

  async *enhanceSubtitlesStream(data: {
    subtitles: { index: number; start_time: number; end_time: number; text: string }[]
    api_key: string
    base_url: string
    model: string
    content_hint?: string
    merge_short?: boolean
    mode?: 'enhance' | 'translate'
    target_language?: string
    bilingual?: boolean
  }): AsyncGenerator<{
    type: string
    batch?: number
    total?: number
    percent?: number
    subtitles?: { index: number; start_time: number; end_time: number; text: string }[]
    message?: string
  }> {
    const res = await fetch(`${BASE}/api/subtitles/enhance`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok || !res.body) {
      const body = await res.json().catch(() => ({}))
      let msg = `Request failed: ${res.status}`
      if (body.detail) {
        msg = typeof body.detail === 'string'
          ? body.detail
          : JSON.stringify(body.detail)
      }
      throw new Error(msg)
    }
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          yield JSON.parse(line.slice(6))
        }
      }
    }
  },

  summarizeSubtitles(taskId: string, data: LlmSummarizeRequest) {
    return request<SubtitleNotes>(`/api/subtitles/${taskId}/summarize`, {
      method: 'POST',
      body: JSON.stringify(data),
    })
  },

  async getSubtitleNotes(taskId: string): Promise<SubtitleNotes | null> {
    const res = await fetch(`${BASE}/api/subtitles/${taskId}/notes`)
    if (res.status === 404) return null
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || `Request failed: ${res.status}`)
    }
    return res.json()
  },
}
