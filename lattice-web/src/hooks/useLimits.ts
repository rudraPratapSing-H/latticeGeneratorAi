import { useQuery } from '@tanstack/react-query'
import { queryKeys } from '@/api/queryKeys'
import { getLimits } from '@/api/endpoints'
import { extractLimits, scaleLimitsForMaterial } from '@/config/limits'
import type { MaterialLimits } from '@/config/limits'

// PROVISIONAL: /api/limits shape is unspecified
export function useLimits(
  materialId: string | undefined,
  materialE?: number,
  materialYield?: number,
) {
  return useQuery({
    queryKey: queryKeys.limits(materialId ?? ''),
    queryFn: async (): Promise<MaterialLimits | null> => {
      if (!materialId) return null
      const raw = await getLimits(materialId)
      const parsed = extractLimits(raw)
      if (parsed) return parsed
      // Fallback to scaled placeholders
      if (materialE && materialYield) {
        return scaleLimitsForMaterial(materialE, materialYield)
      }
      return null
    },
    enabled: !!materialId,
    staleTime: 60_000,
  })
}

