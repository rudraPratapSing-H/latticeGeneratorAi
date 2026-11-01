// OWNED BY TEAMMATE C. Replace the implementation, keep the exported types and names.
// This stub renders an inline SVG placeholder so the app looks complete today.

import type { LatticeViewerProps } from '@/components/LatticeViewer/types'
import { cn } from '@/lib/cn'

/**
 * Lightweight placeholder: renders a simple isometric wireframe of the lattice edges.
 * Does NOT use three.js — keeps the bundle light until teammate C drops in the real viewer.
 */
export function LatticePlaceholder({
  lattice,
  variant = 'thumbnail',
  className,
  colorByAxis,
}: LatticeViewerProps) {
  const nodes = lattice.nodes
  const edges = lattice.edges

  // Simple isometric projection: x' = (x - y) * cos30, y' = (x + y) * sin30 - z
  const cos30 = 0.866
  const sin30 = 0.5
  const scale = variant === 'thumbnail' ? 60 : 100
  const cx = variant === 'thumbnail' ? 80 : 130
  const cy = variant === 'thumbnail' ? 70 : 120

  function project(node: number[]): [number, number] {
    const [x, y, z] = node
    const px = cx + (x - y) * cos30 * scale
    const py = cy + (x + y) * sin30 * scale * 0.6 - z * scale * 0.8
    return [px, py]
  }

  const viewBox = variant === 'thumbnail' ? '0 0 160 140' : '0 0 260 240'

  function edgeColor(edge: number[]): string {
    if (!colorByAxis) return 'var(--color-accent)'
    const [a, b] = edge
    const na = nodes[a]
    const nb = nodes[b]
    if (!na || !nb) return 'var(--color-accent)'

    const dx = Math.abs(na[0] - nb[0])
    const dy = Math.abs(na[1] - nb[1])
    const dz = Math.abs(na[2] - nb[2])

    // Pick dominant axis
    if (dx >= dy && dx >= dz) return 'var(--color-axis-x)'
    if (dy >= dx && dy >= dz) return 'var(--color-axis-y)'
    return 'var(--color-axis-z)'
  }

  return (
    <div
      className={cn(
        'bg-surface-2 relative flex flex-col items-center justify-center overflow-hidden rounded-lg',
        variant === 'thumbnail' ? 'aspect-square' : 'aspect-[4/3]',
        className,
      )}
    >
      <svg viewBox={viewBox} className="h-full w-full" aria-label="Lattice wireframe preview">
        {/* Edges */}
        {edges.map((edge, i) => {
          const a = nodes[edge[0]]
          const b = nodes[edge[1]]
          if (!a || !b) return null
          const [x1, y1] = project(a)
          const [x2, y2] = project(b)
          return (
            <line
              key={i}
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
              stroke={edgeColor(edge)}
              strokeWidth={variant === 'thumbnail' ? 1 : 1.5}
              strokeOpacity={0.7}
            />
          )
        })}

        {/* Nodes */}
        {nodes.map((node, i) => {
          const [px, py] = project(node)
          return (
            <circle
              key={i}
              cx={px}
              cy={py}
              r={variant === 'thumbnail' ? 1.5 : 2.5}
              fill="var(--color-accent)"
              fillOpacity={0.9}
            />
          )
        })}

        {/* Axis gizmo (bottom-left) */}
        {variant === 'full' && (
          <g transform="translate(30, 210)">
            <line x1="0" y1="0" x2="20" y2="-6" stroke="var(--color-axis-x)" strokeWidth="2" />
            <line x1="0" y1="0" x2="-12" y2="-10" stroke="var(--color-axis-y)" strokeWidth="2" />
            <line x1="0" y1="0" x2="0" y2="-22" stroke="var(--color-axis-z)" strokeWidth="2" />
            <text x="24" y="-4" fill="var(--color-axis-x)" fontSize="9" fontFamily="monospace">
              X
            </text>
            <text x="-20" y="-10" fill="var(--color-axis-y)" fontSize="9" fontFamily="monospace">
              Y
            </text>
            <text x="3" y="-24" fill="var(--color-axis-z)" fontSize="9" fontFamily="monospace">
              Z
            </text>
          </g>
        )}
      </svg>
    </div>
  )
}
