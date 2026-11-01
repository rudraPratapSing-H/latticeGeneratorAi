import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { AlertTriangle } from 'lucide-react'

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error('ErrorBoundary caught:', error, errorInfo)
  }

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback

      return (
        <div className="flex flex-col items-center justify-center gap-4 py-16 text-center">
          <AlertTriangle className="text-danger h-12 w-12" />
          <div>
            <h2 className="text-text text-lg font-semibold">Something went wrong</h2>
            <p className="text-muted mt-1 max-w-md text-sm">
              {this.state.error?.message ?? 'An unexpected error occurred.'}
            </p>
          </div>
          <div className="flex gap-3">
            <Button variant="secondary" onClick={() => window.location.reload()}>
              Reload
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                window.location.href = '/'
              }}
            >
              Back to form
            </Button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
