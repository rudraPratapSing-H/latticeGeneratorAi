import { useQuery } from '@tanstack/react-query'
import { queryKeys } from '@/api/queryKeys'
import { getHealth } from '@/api/endpoints'
import type { HealthResponse } from '@/api/types'

export function useHealth() {
  return useQuery<HealthResponse>({
    queryKey: queryKeys.health,
    queryFn: getHealth,
    refetchInterval: 15_000,
    retry: false,
  })
}
