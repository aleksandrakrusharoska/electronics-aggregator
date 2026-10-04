import { Component } from 'react'

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  render() {
    if (!this.state.error) return this.props.children

    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950 p-6">
        <div className="max-w-md w-full text-center space-y-6">

          {/* Icon */}
          <div className="w-16 h-16 mx-auto rounded-2xl bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
            <svg className="w-8 h-8 text-red-500 dark:text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
            </svg>
          </div>

          <div className="space-y-2">
            <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-100">
              Нешто тргна наопаку
            </h1>
            <p className="text-slate-500 dark:text-slate-400 text-sm leading-relaxed">
              Страницата наиде на проблем и не може да продолжи.
              Обидете се со освежување — во повеќето случаи тоа го решава проблемот.
            </p>
          </div>

          <button
            onClick={() => window.location.reload()}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-violet-600 hover:bg-violet-700 text-white text-sm font-medium transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Освежете ја страницата
          </button>

          {/* Collapsed technical detail — not shown by default */}
          <details className="text-left">
            <summary className="text-xs text-slate-300 dark:text-slate-600 cursor-pointer select-none">
              Прикажете детали за грешката
            </summary>
            <pre className="mt-2 p-3 rounded-lg bg-slate-100 dark:bg-slate-800 text-xs text-slate-500 dark:text-slate-400 overflow-auto whitespace-pre-wrap break-all">
              {this.state.error?.message}
            </pre>
          </details>

        </div>
      </div>
    )
  }
}
