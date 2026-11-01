import { useQuery } from '@tanstack/react-query'
import { queryKeys } from '@/api/queryKeys'
import { getMaterials } from '@/api/endpoints'
import type { Material } from '@/api/types'

export function useMaterials() {
  return useQuery<Material[]>({
    queryKey: queryKeys.materials,
    queryFn: getMaterials,
    staleTime: Infinity,
  })
}
