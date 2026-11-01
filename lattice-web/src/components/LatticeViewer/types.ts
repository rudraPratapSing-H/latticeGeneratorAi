// OWNED BY TEAMMATE C. Replace the implementation, keep the exported types and names.

import type { Lattice } from '@/api/types'

export const LATTICE_VIEWER_MAX_TILES = 5

export interface LatticeViewerProps {
  /** Exact contract shape (octant27); the viewer mirrors + merges + tiles itself */
  lattice: Lattice
  /** 1..5 cells per side, default 1 */
  tiles?: number
  /** thumbnail: non-interactive, cheap, no controls; full: orbit/zoom */
  variant?: 'thumbnail' | 'full'
  /** default 'solid' */
  renderMode?: 'solid' | 'wireframe'
  /** default false */
  colorByAxis?: boolean
  /** parent sizes the box; viewer fills 100% width/height */
  className?: string
  onError?: (error: Error) => void
}
