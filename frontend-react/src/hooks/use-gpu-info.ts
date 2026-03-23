import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'

export function useGpuInfo(enabled = false) {
  return useQuery({
    queryKey: ['gpu-info'],
    queryFn: api.getGpuInfo,
    enabled,
    staleTime: 30_000,
  })
}
