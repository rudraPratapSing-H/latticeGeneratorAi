import { useEffect, useMemo, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { cancelJob } from '@/api/endpoints'
import { queryKeys } from '@/api/queryKeys'
import { useJob } from '@/hooks/useJob'
import { useJobEvents } from '@/hooks/useJobEvents'
import { StageStepper } from '@/features/job/StageStepper'
import { ProgressPanel } from '@/features/job/ProgressPanel'
import { RoundsTimeline } from '@/features/job/RoundsTimeline'
import { ActivityLog } from '@/features/job/ActivityLog'
import { TargetChips } from '@/features/job/TargetChips'
import { CandidateGrid } from '@/features/results/CandidateGrid'
import { ComparisonMatrix } from '@/features/results/ComparisonMatrix'
import { ResultsHeader } from '@/features/results/ResultsHeader'
import { ResultsToolbar } from '@/features/results/ResultsToolbar'
import { ResultsBanner } from '@/features/results/ResultsBanner'
import { RequestJsonDialog } from '@/features/design-form/RequestJsonDialog'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { InlineAlert } from '@/components/feedback/InlineAlert'
import { ErrorState } from '@/components/feedback/ErrorState'
import { EmptyState } from '@/components/feedback/EmptyState'
import { useClipboard } from '@/hooks/useClipboard'
import { loadRequest } from '@/lib/storage'
import { fmtDuration } from '@/lib/format'
import type { ApiError } from '@/api/client'
import type { Candidate, DesignRequest } from '@/api/types'
import type { ViewMode, SortKey } from '@/features/results/ResultsToolbar'
import { Copy, Plus, RotateCcw, XCircle } from 'lucide-react'

export default function JobPage() {
  const { jobId } = useParams<{ jobId: string }>()
  const { data: job, isLoading, error, refetch } = useJob(jobId!)
  const isTerminal = job?.status === 'done' || job?.status === 'failed' || job?.status === 'cancelled'
  const events = useJobEvents(jobId!, !isTerminal)

  // Echoed request from backend has priority, otherwise locally stored request
  const storedRequest = useMemo(() => loadRequest(jobId!), [jobId])
  const request: (DesignRequest & { _metadata?: { adjustedFields?: string[] } }) | null =
    (job?.request as DesignRequest) ?? storedRequest

  const [viewMode, setViewMode] = useState<ViewMode>('cards')
  const [sortKey, setSortKey] = useState<SortKey>('rank')
  const [onlyMeeting, setOnlyMeeting] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [showJson, setShowJson] = useState(false)
  const { copy } = useClipboard()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const cancel = useMutation({
    mutationFn: () => cancelJob(jobId!),
    onSuccess: (r) => {
      toast.info(r.status === 'cancelled' ? 'Run cancelled' : 'Stopping after the current search round…')
      void queryClient.invalidateQueries({ queryKey: queryKeys.job(jobId!) })
    },
    onError: () => toast.error('Could not cancel the run'),
  })

  // Elapsed timer
  useEffect(() => {
    if (isTerminal) return
    const start = Date.now()
    const timer = setInterval(() => setElapsed((Date.now() - start) / 1000), 1000)
    return () => clearInterval(timer)
  }, [isTerminal])

  // Update document title
  useEffect(() => {
    if (job?.status === 'done') {
      document.title = `Results · ${jobId} · Lattice Designer`
    } else {
      document.title = `${job?.status ?? 'Loading'} · ${jobId} · Lattice Designer`
    }
  }, [job?.status, jobId])

  // Merge polled and event progress (monotonic)
  const progress = Math.max(job?.progress ?? 0, events.progress)
  const stage = events.stage ?? job?.stage ?? null
  const message =
    events.messages.length > 0
      ? events.messages[events.messages.length - 1].message
      : (job?.message ?? 'Starting…')

  // Loading
  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-4 w-64" />
        <Skeleton className="h-20" />
        <Skeleton className="h-40" />
      </div>
    )
  }

  // Error
  if (error) {
    const apiErr = error as ApiError
    if (apiErr.code === 'not_found' || apiErr.status === 404) {
      return (
        <ErrorState
          title="We couldn't find this run"
          message={`Job ${jobId} doesn't exist or has expired.`}
          onBack={() => navigate('/')}
        />
      )
    }
    return (
      <ErrorState
        error={apiErr}
        onRetry={() => {
          refetch()
        }}
        onBack={() => navigate('/')}
      />
    )
  }

  if (!job) return null

  // CANCELLED
  if (job.status === 'cancelled' && job.candidates.length === 0) {
    return (
      <div className="animate-fade-in space-y-6">
        <PageHeader title={`Run ${jobId}`} />
        <ErrorState
          title="This run was cancelled"
          message={job.message || 'The search job was cancelled before finishing.'}
          onBack={() => navigate('/')}
          backLabel="Back to design form"
        />
      </div>
    )
  }

  // FAILED
  if (job.status === 'failed') {
    return (
      <div className="space-y-6 animate-fade-in">
        <PageHeader title={`Run ${jobId}`} />
        <ErrorState
          title="Job failed"
          message={job.message}
          onBack={() => navigate('/')}
        />
        <div className="flex justify-center gap-3">
          <Link to="/">
            <Button variant="secondary" size="sm">
              <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
              Edit target & retry
            </Button>
          </Link>
          <Link to="/">
            <Button variant="outline" size="sm">
              <Plus className="mr-1.5 h-3.5 w-3.5" />
              New design
            </Button>
          </Link>
        </div>
      </div>
    )
  }

  // QUEUED / RUNNING
  if (job.status === 'queued' || job.status === 'running') {
    const queueMsg = job.queue_position
      ? `Waiting in queue (position ${job.queue_position})`
      : 'Waiting in queue'

    return (
      <div className="animate-fade-in space-y-6">
        <PageHeader title={`Run ${jobId}`}>
          <div className="flex items-center gap-3">
            <span className="text-muted font-mono text-sm tabular-nums">
              {fmtDuration(elapsed)}
            </span>
            <button
              onClick={() => copy(jobId!, 'Job ID copied')}
              className="text-muted hover:text-text cursor-pointer"
              aria-label="Copy job ID"
            >
              <Copy className="h-4 w-4" />
            </button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => cancel.mutate()}
              disabled={cancel.isPending}
            >
              <XCircle className="mr-1.5 h-3.5 w-3.5" />
              Cancel run
            </Button>
          </div>
        </PageHeader>

        <p className="text-muted text-xs">
          This run continues in the background. You can leave this page; this URL reopens it.
        </p>

        {job.warnings && job.warnings.length > 0 && (
          <div className="space-y-1">
            {job.warnings.map((w, i) => (
              <InlineAlert key={i} variant="warning">
                {w}
              </InlineAlert>
            ))}
          </div>
        )}

        <Card className="space-y-6 p-5 sm:p-6">
          <StageStepper currentStage={stage} status={job.status} />
          <div className="rule-fade" />
          <ProgressPanel
            progress={job.status === 'queued' ? 0 : progress}
            message={job.status === 'queued' ? queueMsg : message}
          />
        </Card>

        {job.reach && (
          <div className="flex items-center gap-2 text-xs">
            <span className="text-muted">Dataset reach:</span>
            <Badge variant="accent">
              {job.reach.level} ({job.reach.distance_pct.toFixed(1)}% distance)
            </Badge>
          </div>
        )}

        {request && <TargetChips request={request} />}

        {job.rounds && job.rounds.length > 0 && (
          <RoundsTimeline rounds={job.rounds} currentRound={job.round} />
        )}

        <ActivityLog messages={events.messages} className="mt-4" />
      </div>
    )
  }

  // DONE — results
  const candidates = job.candidates
  const sortedCandidates = sortCandidates(candidates, sortKey)

  // Rule 1: The solver decides. Never present a design as a match unless server says matches_targets
  const filteredCandidates = onlyMeeting
    ? sortedCandidates.filter((c) => c.matches_targets)
    : sortedCandidates

  return (
    <div className="animate-fade-in space-y-6">
      <ResultsHeader
        jobId={jobId!}
        candidateCount={candidates.length}
        candidates={candidates}
        request={request}
        onShowJson={() => setShowJson(true)}
      />

      {job.status === 'cancelled' && (
        <InlineAlert variant="warning">
          This run was cancelled. {job.message || 'Showing the best designs found so far.'}
        </InlineAlert>
      )}

      <ResultsBanner
        candidates={candidates}
        request={request}
        reach={job.reach}
        infeasible={job.infeasible}
        warnings={job.warnings}
      />

      {candidates.length === 0 && (
        <EmptyState
          title="No designs came back"
          message="No valid design met the constraints. Try relaxing the tolerance, raising the mass limit, or reducing stiffness."
        >
          <Link to="/">
            <Button variant="secondary" size="sm">
              Edit target
            </Button>
          </Link>
        </EmptyState>
      )}

      {candidates.length > 0 && (
        <ResultsToolbar
          viewMode={viewMode}
          onViewModeChange={setViewMode}
          sortKey={sortKey}
          onSortKeyChange={setSortKey}
          onlyMeeting={onlyMeeting}
          onOnlyMeetingChange={setOnlyMeeting}
          request={request}
        />
      )}

      {filteredCandidates.length === 0 && onlyMeeting && candidates.length > 0 && (
        <EmptyState
          title="No design meets every target"
          message="Try turning off the filter to see all results."
        >
          <Button variant="ghost" size="sm" onClick={() => setOnlyMeeting(false)}>
            Show all
          </Button>
        </EmptyState>
      )}

      {filteredCandidates.length > 0 && viewMode === 'cards' && (
        <CandidateGrid candidates={filteredCandidates} jobId={jobId!} request={request} />
      )}

      {filteredCandidates.length > 0 && viewMode === 'compare' && (
        <ComparisonMatrix candidates={filteredCandidates} jobId={jobId!} request={request} />
      )}

      {job.rounds && job.rounds.length > 0 && (
        <div className="mt-8 border-t border-line/60 pt-6">
          <RoundsTimeline rounds={job.rounds} currentRound={job.round} />
        </div>
      )}

      {!request && candidates.length > 0 && (
        <p className="text-muted text-center text-xs">
          Target not available for this run (opened in a different browser). Pass/fail markers are
          hidden.
        </p>
      )}

      {request && (
        <RequestJsonDialog open={showJson} onOpenChange={setShowJson} request={request} />
      )}
    </div>
  )
}

function sortCandidates(candidates: Candidate[], key: SortKey): Candidate[] {
  const sorted = [...candidates]
  switch (key) {
    case 'rank':
      return sorted.sort((a, b) => a.rank - b.rank)
    case 'match_error':
      return sorted.sort((a, b) => a.match_error_pct - b.match_error_pct)
    case 'mass':
      return sorted.sort((a, b) => a.mass_g - b.mass_g)
    case 'rel_density':
      return sorted.sort((a, b) => a.rel_density - b.rel_density)
    default:
      return sorted
  }
}
