import { useQuery } from '@tanstack/react-query'
import { queryKeys } from '@/api/queryKeys'
import { getDesign } from '@/api/endpoints'
import type { Candidate } from '@/api/types'

export function useDesign(designId: string, options: { enabled: boolean }) {
  return useQuery<Candidate>({
    queryKey: queryKeys.design(designId),
    queryFn: () => getDesign(designId),
    enabled: options.enabled,
  })
}
