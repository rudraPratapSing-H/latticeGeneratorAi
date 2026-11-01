import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { useClipboard } from '@/hooks/useClipboard'
import type { DesignRequest } from '@/api/types'
import { Copy } from 'lucide-react'

interface RequestJsonDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  request: DesignRequest
}

export function RequestJsonDialog({ open, onOpenChange, request }: RequestJsonDialogProps) {
  const { copy } = useClipboard()
  const json = JSON.stringify(request, null, 2)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogTitle>Request JSON</DialogTitle>
        <div className="mt-4 space-y-3">
          <pre className="bg-surface-2 text-text max-h-96 overflow-x-auto rounded-lg p-4 font-mono text-xs">
            {json}
          </pre>
          <Button variant="ghost" size="sm" onClick={() => copy(json, 'JSON copied')}>
            <Copy className="h-3.5 w-3.5" />
            Copy JSON
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
