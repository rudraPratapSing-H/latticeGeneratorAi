import { useQuery } from '@tanstack/react-query'
import { queryKeys } from '@/api/queryKeys'
import { getJob } from '@/api/endpoints'
import { USE_MOCK } from '@/config/env'
import type { Candidate, Job } from '@/api/types'

export function useJob(jobId: string) {
  return useQuery<Job>({
    queryKey: queryKeys.job(jobId),
    queryFn: () => getJob(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (status === 'done' || status === 'failed' || status === 'cancelled') return false
      return USE_MOCK ? 1000 : 1500
    },
  })
}

/** Select a single candidate from the job data */
export function useCandidateFromJob(jobId: string, designId: string) {
  return useQuery<Job, Error, Candidate | undefined>({
    queryKey: queryKeys.job(jobId),
    queryFn: () => getJob(jobId),
    select: (job) => job.candidates.find((c) => c.id === designId),
    refetchInterval: false,
  })
}
