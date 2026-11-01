import { Link } from 'react-router-dom'
import type { Candidate } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { designPath, jobPath } from '@/config/constants'
import { fmtPct } from '@/lib/format'
import { ArrowLeft, ArrowRight, ChevronLeft } from 'lucide-react'

interface DetailHeaderProps {
  candidate: Candidate
  jobId: string
  prevId: string | null
  nextId: string | null
  tolerance: number
  fromImplant?: string | null
}

export function DetailHeader({
  candidate,
  jobId,
  prevId,
  nextId,
  tolerance,
  fromImplant,
}: DetailHeaderProps) {
  const backUrl = fromImplant ? `/implant/${fromImplant}/results` : jobPath(jobId)
  const implantParam = fromImplant ? `?fromImplant=${fromImplant}` : ''

  return (
    <>
      {/* Title + nav */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Link to={backUrl} className="text-muted hover:text-text" title={fromImplant ? 'Back to implant candidates' : 'Back to results'}>
            <ChevronLeft className="h-5 w-5" />
          </Link>
          <h1 className="text-text text-xl font-semibold">
            Design <span className="text-accent font-mono">{candidate.id}</span>
          </h1>
          <Badge
            variant={
              candidate.matches_targets
                ? 'success'
                : candidate.match_error_pct <= tolerance * 2
                  ? 'warning'
                  : 'danger'
            }
          >
            #{candidate.rank} · {fmtPct(candidate.match_error_pct)} error
          </Badge>
          {fromImplant && (
            <Badge variant="neutral" className="text-xs">
              Implant Zone Candidate
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-2">
          {prevId && (
            <Link to={designPath(jobId, prevId) + implantParam}>
              <Button variant="ghost" size="sm" aria-label="Previous design">
                <ArrowLeft className="h-4 w-4" />
              </Button>
            </Link>
          )}
          {nextId && (
            <Link to={designPath(jobId, nextId) + implantParam}>
              <Button variant="ghost" size="sm" aria-label="Next design">
                <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
          )}
        </div>
      </div>

      {/* Breadcrumb */}
      <nav className="text-muted flex items-center gap-1.5 text-xs">
        {fromImplant ? (
          <>
            <Link to="/implant" className="hover:text-accent">
              Implant
            </Link>
            <span>›</span>
            <Link to={`/implant/${fromImplant}/results`} className="hover:text-accent font-mono">
              Zone Candidates
            </Link>
            <span>›</span>
            <span className="text-accent font-mono">{candidate.id}</span>
          </>
        ) : (
          <>
            <Link to="/" className="hover:text-accent">
              Design
            </Link>
            <span>›</span>
            <Link to={jobPath(jobId)} className="hover:text-accent font-mono">
              {jobId}
            </Link>
            <span>›</span>
            <span className="text-accent font-mono">{candidate.id}</span>
          </>
        )}
      </nav>
    </>
  )
}
