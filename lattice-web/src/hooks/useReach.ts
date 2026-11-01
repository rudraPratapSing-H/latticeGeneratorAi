import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { queryKeys } from '@/api/queryKeys'
import { checkReach } from '@/api/endpoints'
import type { DesignRequest, ReachResponse } from '@/api/types'

/**
 * Checks a design request against the dataset.
 * Debounced by the caller via a stable hash; keeps previous data while loading.
 */
export function useReach(request: DesignRequest | null, hash: string) {
  return useQuery<ReachResponse>({
    queryKey: queryKeys.reach(hash),
    queryFn: () => checkReach(request!),
    enabled: !!request && hash !== '',
    staleTime: 10_000,
    placeholderData: keepPreviousData,
    retry: false,
  })
}

