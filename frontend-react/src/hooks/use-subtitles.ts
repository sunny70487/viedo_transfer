import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { toast } from '@/stores/toast-store'
import type { SubtitleCollection } from '@/types/api'

export function useSubtitles(taskId: string) {
  return useQuery({
    queryKey: ['subtitles', taskId],
    queryFn: () => api.getSubtitles(taskId),
    enabled: !!taskId,
    staleTime: Infinity,
  })
}

export function useSaveSubtitles(taskId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: SubtitleCollection) => api.saveSubtitles(taskId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['subtitles', taskId] })
      toast('success', '字幕已儲存')
    },
    onError: (err: Error) => {
      toast('error', `儲存失敗: ${err.message}`)
    },
  })
}
