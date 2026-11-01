import { useState } from 'react'
import type { LatticeViewerProps } from '@/components/LatticeViewer/types'
import { LatticePlaceholder } from '@/components/LatticeViewer/LatticePlaceholder'
import { LatticeCanvas } from '@/components/LatticeViewer/LatticeCanvas'
import { LatticeThumb } from '@/components/LatticeViewer/LatticeThumb'

/**
 * Check if WebGL context is available in the current environment
 */
function hasWebGLSupport(): boolean {
  if (typeof window === 'undefined') return false
  try {
    const canvas = document.createElement('canvas')
    const gl =
      canvas.getContext('webgl') ||
      canvas.getContext('experimental-webgl')
    return !!(gl && typeof (gl as WebGLRenderingContext).getExtension === 'function')
  } catch {
    return false
  }
}

/**
 * Interactive 3D Lattice Viewer with motion and tiling support.
 *
 * - variant='full': Rich 3D WebGL Canvas with OrbitControls, continuous 3D rotation motion,
 *   tiling from 1 to 5 cells, camera auto-framing, and studio lighting.
 * - variant='thumbnail': Lightweight SVG wireframe so multiple candidate cards mount smoothly.
 * - Graceful fallback to LatticePlaceholder in headless/test environments or on WebGL error.
 */
export default function LatticeViewer(props: LatticeViewerProps & { active?: boolean; seedKey?: string }) {
  const [canRender3D] = useState(hasWebGLSupport)
  const [hasError, setHasError] = useState(false)

  const handleError = (error: Error) => {
    setHasError(true)
    props.onError?.(error)
  }

  // Use 3D WebGL for full view when supported and no error occurred
  if (canRender3D && !hasError && props.variant === 'full') {
    return (
      <LatticeCanvas
        lattice={props.lattice}
        tiles={props.tiles ?? 1}
        renderMode={props.renderMode ?? 'solid'}
        colorByAxis={props.colorByAxis ?? false}
        className={props.className}
        onError={handleError}
      />
    )
  }

  // Thumbnails: rotating 3D through one shared renderer (falls back to the SVG wireframe by itself)
  if (canRender3D && props.variant === 'thumbnail') {
    return <LatticeThumb {...props} />
  }

  // Fallback placeholder (fast, accessible, renders in all environments including tests)
  return <LatticePlaceholder {...props} />
}
