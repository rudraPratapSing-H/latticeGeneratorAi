import { useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { createDesign } from '@/api/endpoints'
import { saveRequest, addRecentRun } from '@/lib/storage'
import { jobPath } from '@/config/constants'
import type { DesignRequest } from '@/api/types'

export type CreateDesignInput =
  | DesignRequest
  | { request: DesignRequest; metadata?: { adjustedFields?: string[] } }

export function useCreateDesign() {
  const navigate = useNavigate()

  return useMutation({
    mutationFn: (input: CreateDesignInput) => {
      const req = 'request' in input ? input.request : input
      return createDesign(req)
    },
    onSuccess: (data, input) => {
      const { job_id } = data
      const req = 'request' in input ? input.request : input
      const metadata = 'metadata' in input ? input.metadata : undefined

      // Save the request with frontend-only metadata for later display
      saveRequest(job_id, req, metadata)

      // Add to recent runs
      const stiffX = 'stiffness_gpa' in req.target ? req.target.stiffness_gpa.x : null
      const summary = stiffX !== null ? `Stiffness X: ${stiffX} GPa` : 'Custom design'

      addRecentRun({
        jobId: job_id,
        material: req.material,
        summary,
        timestamp: Date.now(),
      })

      navigate(jobPath(job_id))
    },
  })
}
