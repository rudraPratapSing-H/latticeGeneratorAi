import { useCallback, useState } from 'react'
import { toast } from 'sonner'

export function useClipboard() {
  const [copied, setCopied] = useState(false)

  const copy = useCallback(async (text: string, label = 'Copied') => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      toast.success(label)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      toast.error('Failed to copy')
    }
  }, [])

  return { copied, copy }
}
