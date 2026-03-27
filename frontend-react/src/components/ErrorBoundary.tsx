import { Component, type ReactNode } from 'react'

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error?: Error
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('ErrorBoundary caught:', error, info)
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback
      return (
        <div className="min-h-screen flex items-center justify-center bg-bg dark:bg-bg-dark">
          <div className="text-center p-8 max-w-md">
            <div className="mx-auto mb-4 h-16 w-16 rounded-full bg-danger/10 flex items-center justify-center">
              <svg className="h-8 w-8 text-danger" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <h2 className="text-xl font-bold text-text dark:text-text-dark mb-2">
              應用程式發生錯誤
            </h2>
            <p className="text-muted dark:text-muted-dark mb-6 text-sm">
              {this.state.error?.message || '發生了未預期的錯誤'}
            </p>
            <button
              onClick={() => globalThis.location.reload()}
              className="px-6 py-2.5 bg-primary text-white rounded-lg hover:bg-primary-hover transition-colors font-medium"
            >
              重新載入頁面
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
