import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { useClipboard } from '@/hooks/useClipboard'
import type { DesignRequest } from '@/api/types'
import { Copy, Download, Plus, Code2 } from 'lucide-react'
import { toast } from 'sonner'
import type { Candidate } from '@/api/types'

interface ResultsHeaderProps {
  jobId: string
  candidateCount: number
  candidates: Candidate[]
  request: DesignRequest | null
  onShowJson: () => void
}

export function ResultsHeader({
  jobId,
  candidateCount,
  candidates,
  request,
  onShowJson,
}: ResultsHeaderProps) {
  const { copy } = useClipboard()

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-text text-2xl font-semibold tracking-tight sm:text-3xl">{candidateCount} designs found</h1>
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => copy(window.location.href, 'Link copied')}
            className="text-muted hover:text-text cursor-pointer"
            aria-label="Copy link"
          >
            <Copy className="h-4 w-4" />
          </button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              const blob = new Blob([JSON.stringify(candidates, null, 2)], {
                type: 'application/json',
              })
              const url = URL.createObjectURL(blob)
              const a = document.createElement('a')
              a.href = url
              a.download = `results_${jobId}.json`
              a.click()
              URL.revokeObjectURL(url)
              toast.success('Results JSON downloaded')
            }}
          >
            <Download className="h-3.5 w-3.5" />
            Export JSON
          </Button>
          {request && (
            <Button variant="ghost" size="sm" onClick={onShowJson}>
              <Code2 className="h-3.5 w-3.5" />
              Request
            </Button>
          )}
          <Link to="/">
            <Button variant="secondary" size="sm">
              <Plus className="h-3.5 w-3.5" />
              New design
            </Button>
          </Link>
        </div>
      </div>

      <nav className="text-muted flex items-center gap-1.5 text-xs">
        <Link to="/" className="hover:text-accent">
          Design
        </Link>
        <span>›</span>
        <span className="text-accent font-mono">{jobId}</span>
      </nav>
    </>
  )
}
