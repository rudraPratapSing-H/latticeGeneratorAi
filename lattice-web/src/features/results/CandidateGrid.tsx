import type { Candidate, DesignRequest } from '@/api/types'
import { CandidateCard } from '@/features/results/CandidateCard'

interface CandidateGridProps {
  candidates: Candidate[]
  jobId: string
  request: DesignRequest | null
}

export function CandidateGrid({ candidates, jobId, request }: CandidateGridProps) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {candidates.map((c, i) => (
        <CandidateCard key={c.id} candidate={c} jobId={jobId} request={request} index={i} />
      ))}
    </div>
  )
}
