import { useState } from 'react'
import type { Candidate, DesignRequest } from '@/api/types'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from '@/components/ui/dropdown-menu'
import { useClipboard } from '@/hooks/useClipboard'
import { buildStlBuffer } from '@/lib/stl'
import { MAX_STL_TILES, MAX_VIEWER_TILES } from '@/config/constants'
import { Copy, Download, Loader2 } from 'lucide-react'
import { toast } from 'sonner'

interface DownloadMenuProps {
  candidate: Candidate
  tiles: number
  request?: DesignRequest | null
}

export function DownloadMenu({ candidate, tiles, request }: DownloadMenuProps) {
  const { copy } = useClipboard()
  const [stlLoading, setStlLoading] = useState(false)

  const handleDownloadStl = async () => {
    setStlLoading(true)
    try {
      let tileCounts: [number, number, number] = [tiles, tiles, tiles]
      if (request?.part) {
        const cx = Math.max(1, Math.min(MAX_STL_TILES, Math.round(request.part.size_mm[0] / request.part.cell_mm)))
        const cy = Math.max(1, Math.min(MAX_STL_TILES, Math.round(request.part.size_mm[1] / request.part.cell_mm)))
        const cz = Math.max(1, Math.min(MAX_STL_TILES, Math.round(request.part.size_mm[2] / request.part.cell_mm)))
        tileCounts = [cx, cy, cz]
      }

      if (tileCounts.some((t) => t > MAX_VIEWER_TILES)) {
        toast.warning(`Exporting high tile count (${tileCounts.join('×')}). May result in a large file.`)
      }

      const result = buildStlBuffer(candidate.lattice, { tiles: tileCounts, filename: `${candidate.id}.stl` })
      if (result.reducedSides) {
        toast.warning(
          `Large file (${(result.triangles / 1e6).toFixed(1)} M triangles): struts built with 8 sides instead of 12.`,
        )
      }
      const blob = new Blob([result.buffer], { type: 'model/stl' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${candidate.id}.stl`
      a.click()
      URL.revokeObjectURL(url)
      toast.success('STL downloaded')
    } catch (err) {
      toast.error(`STL export failed: ${err instanceof Error ? err.message : 'unknown error'}`)
    } finally {
      setStlLoading(false)
    }
  }

  const handleDownloadJson = () => {
    const blob = new Blob([JSON.stringify(candidate, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${candidate.id}.json`
    a.click()
    URL.revokeObjectURL(url)
    toast.success('Design JSON downloaded')
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="secondary" className="w-full sm:w-auto" disabled={stlLoading}>
          {stlLoading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Download className="h-4 w-4" />
          )}
          Download
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuItem onClick={handleDownloadStl} disabled={stlLoading}>
          Download STL (.stl)
        </DropdownMenuItem>
        <DropdownMenuItem onClick={handleDownloadJson}>
          Download design JSON (.json)
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => copy(candidate.id, 'Design ID copied')}>
          <Copy className="h-3.5 w-3.5" />
          Copy design ID
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
