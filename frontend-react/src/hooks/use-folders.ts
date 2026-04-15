import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { toast } from '@/stores/toast-store'

export function useFolders() {
  return useQuery({
    queryKey: ['folders'],
    queryFn: api.getFolders,
    refetchInterval: 30_000,
  })
}

export function useCreateFolder() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ name, parentId }: { name: string; parentId?: string | null }) =>
      api.createFolder(name, parentId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['folders'] })
      toast('success', '資料夾已建立')
    },
    onError: (err: Error) => {
      toast('error', `建立資料夾失敗: ${err.message}`)
    },
  })
}

export function useRenameFolder() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ folderId, name }: { folderId: string; name: string }) =>
      api.renameFolder(folderId, name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['folders'] })
      toast('success', '資料夾已重命名')
    },
    onError: (err: Error) => {
      toast('error', `重命名失敗: ${err.message}`)
    },
  })
}

export function useDeleteFolder() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (folderId: string) => api.deleteFolder(folderId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['folders'] })
      qc.invalidateQueries({ queryKey: ['tasks'] })
      toast('success', '資料夾已刪除')
    },
    onError: (err: Error) => {
      toast('error', `刪除資料夾失敗: ${err.message}`)
    },
  })
}

export function useMoveTasksToFolder() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ folderId, taskIds }: { folderId: string; taskIds: string[] }) =>
      api.moveTasksToFolder(folderId, taskIds),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['folders'] })
      qc.invalidateQueries({ queryKey: ['tasks'] })
      toast('success', '任務已移動')
    },
    onError: (err: Error) => {
      toast('error', `移動任務失敗: ${err.message}`)
    },
  })
}

export function useRemoveTasksFromFolder() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ folderId, taskIds }: { folderId: string; taskIds: string[] }) =>
      api.removeTasksFromFolder(folderId, taskIds),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['folders'] })
      qc.invalidateQueries({ queryKey: ['tasks'] })
      toast('success', '任務已從資料夾移除')
    },
    onError: (err: Error) => {
      toast('error', `移除失敗: ${err.message}`)
    },
  })
}

export function useReorderTasks() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ folderId, taskIds }: { folderId: string; taskIds: string[] }) =>
      api.reorderTasks(folderId, taskIds),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
    },
    onError: (err: Error) => {
      toast('error', `排序失敗: ${err.message}`)
    },
  })
}

export function useReorderFolders() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (folderIds: string[]) => api.reorderFolders(folderIds),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['folders'] })
    },
    onError: (err: Error) => {
      toast('error', `排序失敗: ${err.message}`)
    },
  })
}

export function useTranscribeFolderUpload() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      files,
      relativePaths,
      folderName,
      params,
    }: {
      files: File[]
      relativePaths: string[]
      folderName: string
      params: Record<string, string>
    }) => api.transcribeFolderUpload(files, relativePaths, folderName, params),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      qc.invalidateQueries({ queryKey: ['folders'] })
      const msg = `已提交 ${data.task_ids.length} 個資料夾轉錄任務`
      toast('info', data.errors?.length ? `${msg}（${data.errors.length} 個失敗）` : msg)
    },
    onError: (err: Error) => {
      toast('error', `資料夾上傳失敗: ${err.message}`)
    },
  })
}
