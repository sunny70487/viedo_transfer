import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { toast } from '@/stores/toast-store'

export function useTasks() {
  return useQuery({
    queryKey: ['tasks'],
    queryFn: api.getTasks,
    refetchInterval: 10_000,
  })
}

export function useTask(taskId: string) {
  return useQuery({
    queryKey: ['task', taskId],
    queryFn: () => api.getTask(taskId),
    enabled: !!taskId,
    refetchInterval: false,
  })
}

export function useDeleteTask() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.deleteTask,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      toast('success', '任務已刪除')
    },
    onError: (err: Error) => {
      toast('error', `刪除失敗: ${err.message}`)
    },
  })
}

export function useTranscribeUrl() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.transcribeUrl,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      toast('info', '轉錄任務已提交')
    },
    onError: (err: Error) => {
      toast('error', `提交失敗: ${err.message}`)
    },
  })
}

export function useTranscribeUpload() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ file, params }: { file: File; params: Record<string, string> }) =>
      api.transcribeUpload(file, params),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      toast('info', '上傳轉錄任務已提交')
    },
    onError: (err: Error) => {
      toast('error', `上傳失敗: ${err.message}`)
    },
  })
}

export function useTranscribeBatchUrls() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.transcribeBatchUrls,
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      const msg = `已提交 ${data.task_ids.length} 個批次任務`
      toast('info', data.errors?.length ? `${msg}（${data.errors.length} 個失敗）` : msg)
    },
    onError: (err: Error) => {
      toast('error', `批次提交失敗: ${err.message}`)
    },
  })
}

export function useTranscribeBatchUpload() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ files, params }: { files: File[]; params: Record<string, string> }) =>
      api.transcribeBatchUpload(files, params),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      const msg = `已提交 ${data.task_ids.length} 個批次上傳任務`
      toast('info', data.errors?.length ? `${msg}（${data.errors.length} 個失敗）` : msg)
    },
    onError: (err: Error) => {
      toast('error', `批次上傳失敗: ${err.message}`)
    },
  })
}
