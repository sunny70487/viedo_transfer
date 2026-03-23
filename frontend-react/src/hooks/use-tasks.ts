import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'

export function useTasks() {
  return useQuery({
    queryKey: ['tasks'],
    queryFn: api.getTasks,
    refetchInterval: 3000,
  })
}

export function useTask(taskId: string) {
  return useQuery({
    queryKey: ['task', taskId],
    queryFn: () => api.getTask(taskId),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'completed' || status === 'failed' ? false : 2000
    },
  })
}

export function useDeleteTask() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.deleteTask,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tasks'] }),
  })
}

export function useTranscribeUrl() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.transcribeUrl,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tasks'] }),
  })
}

export function useTranscribeUpload() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ file, params }: { file: File; params: Record<string, string> }) =>
      api.transcribeUpload(file, params),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tasks'] }),
  })
}
