import { useEffect, useRef, useState } from 'react'
import type { LatticeViewerProps } from '@/components/LatticeViewer/types'
import { LatticePlaceholder } from '@/components/LatticeViewer/LatticePlaceholder'
import { attachThumbnail, type ThumbHandle } from '@/components/LatticeViewer/thumbRenderer'
import { cn } from '@/lib/cn'

function seedOf(lattice: LatticeViewerProps['lattice'], key?: string): number {
  let h = 17
  for (const ch of key ?? '') h = (Math.imul(h, 33) + ch.charCodeAt(0)) | 0
  for (const n of lattice.nodes.slice(0, 8)) for (const v of n) h = (Math.imul(h, 31) + Math.round(v * 1000)) | 0
  return Math.abs(h)
}

/**
 * A slowly rotating 3D candidate for a results card. All thumbnails share one WebGL renderer
 * (see thumbRenderer.ts); the frame is copied into this card's own canvas.
 */
export function LatticeThumb(props: LatticeViewerProps & { active?: boolean; seedKey?: string }) {
  const { lattice, className, active = false, seedKey } = props
  const ref = useRef<HTMLCanvasElement>(null)
  const handle = useRef<ThumbHandle | null>(null)
  const [broken, setBroken] = useState(false)

  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const fit = () => {
      const r = canvas.getBoundingClientRect()
      const px = Math.max(96, Math.min(512, Math.round(Math.min(r.width, r.height) * Math.min(window.devicePixelRatio || 1, 2))))
      if (canvas.width !== px) {
        canvas.width = px
        canvas.height = px
      }
    }
    fit()
    const h = attachThumbnail(canvas, lattice, seedOf(lattice, seedKey), () => setBroken(true))
    if (!h) {
      setBroken(true)
      return
    }
    handle.current = h
    const ro = new ResizeObserver(fit)
    ro.observe(canvas)
    return () => {
      ro.disconnect()
      h.dispose()
      handle.current = null
    }
  }, [lattice, seedKey])

  useEffect(() => {
    handle.current?.setHover(active)
  }, [active])

  if (broken) return <LatticePlaceholder {...props} />
  return (
    <canvas
      ref={ref}
      role="img"
      aria-label="Rotating 3D preview of the lattice cell"
      className={cn('block h-full w-full', className)}
    />
  )
}
