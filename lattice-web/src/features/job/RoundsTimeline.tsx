import type { RoundInfo } from '@/api/types'
import { Check, Minus } from 'lucide-react'

interface RoundsTimelineProps {
  rounds: RoundInfo[]
  currentRound?: number
}

export function RoundsTimeline({ rounds, currentRound }: RoundsTimelineProps) {
  if (rounds.length === 0) return null

  return (
    <div className="space-y-2 rounded-xl border border-line bg-surface p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-text">Search Rounds</h3>
        {currentRound && (
          <span className="text-xs font-mono text-accent">
            Round {currentRound} of up to 3
          </span>
        )}
      </div>

      <p className="text-xs text-muted">
        The search tries again with more candidates until a design matches, gains little, or time runs out.
      </p>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-line text-muted">
              <th scope="col" className="pb-2 font-medium">Round</th>
              <th scope="col" className="pb-2 font-medium">Candidates (K)</th>
              <th scope="col" className="pb-2 font-medium">Best Error</th>
              <th scope="col" className="pb-2 font-medium">Matched</th>
              <th scope="col" className="pb-2 font-medium">Evaluated</th>
              <th scope="col" className="pb-2 font-medium">Time</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line/50 font-mono tabular-nums">
            {rounds.map((r) => (
              <tr key={r.round} className="text-text">
                <td className="py-2 font-sans font-medium">Round {r.round}</td>
                <td className="py-2">K = {r.k}</td>
                <td className="py-2 text-accent font-medium">
                  {r.best_error_pct.toFixed(1)}%
                </td>
                <td className="py-2">
                  {r.matched ? (
                    <span className="inline-flex items-center gap-1 text-success font-sans">
                      <Check className="h-3.5 w-3.5" /> Matched
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-muted font-sans">
                      <Minus className="h-3.5 w-3.5" /> No match
                    </span>
                  )}
                </td>
                <td className="py-2">{r.n_candidates}</td>
                <td className="py-2 text-muted">{r.round_seconds.toFixed(1)}s</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

