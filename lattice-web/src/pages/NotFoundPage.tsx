import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { FileQuestion } from 'lucide-react'

export default function NotFoundPage() {
  useEffect(() => {
    document.title = 'Not Found · Lattice Designer'
  }, [])

  return (
    <div className="flex flex-col items-center justify-center gap-4 py-20 text-center">
      <FileQuestion className="text-faint h-16 w-16" />
      <h1 className="text-text text-2xl font-semibold">Page not found</h1>
      <p className="text-muted text-sm">The page you're looking for doesn't exist.</p>
      <Link to="/">
        <Button>Back to designer</Button>
      </Link>
    </div>
  )
}
