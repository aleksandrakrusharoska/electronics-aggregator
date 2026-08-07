import { useState, useEffect, useRef } from 'react'

export default function Header({ stats, theme, onThemeToggle, q, onSearch, wishlistCount, onWishlistOpen, page, onPageChange }) {
  const [input, setInput] = useState(q || '')
  const timerRef = useRef(null)

  useEffect(() => {
    setInput(q || '')
  }, [q])

  const handleChange = e => {
    const val = e.target.value
    setInput(val)
    clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => onSearch(val), 350)
  }

  const handleKey = e => {
    if (e.key === 'Enter') {
      clearTimeout(timerRef.current)
      onSearch(input)
    }
    if (e.key === 'Escape') {
      setInput('')
      clearTimeout(timerRef.current)
      onSearch('')
    }
  }

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200 dark:border-slate-800 bg-white/90 dark:bg-slate-950/90 backdrop-blur-md">
      <div className="flex items-center gap-4 px-6 h-14">

        {/* Logo */}
        <div className="flex items-center gap-2 shrink-0">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-violet-500 to-violet-700 flex items-center justify-center shadow-sm">
            <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18" />
            </svg>
          </div>
          <div className="leading-tight">
            <div className="font-semibold text-sm tracking-tight text-slate-900 dark:text-slate-100">
              Техника <span className="text-slate-400 dark:text-slate-500 font-normal">· агрегатор</span>
            </div>
          </div>
        </div>

        {/* Nav tabs */}
        <div className="flex items-center gap-1 shrink-0">
          {[['ads', 'Огласи'], ['analytics', 'Аналитика']].map(([key, label]) => (
            <button
              key={key}
              onClick={() => onPageChange(key)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                page === key
                  ? 'bg-violet-100 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300'
                  : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Search */}
        <div className="flex-1 max-w-xl relative">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            className="input-base pl-9 pr-8"
            placeholder="Пребарај огласи..."
            value={input}
            onChange={handleChange}
            onKeyDown={handleKey}
          />
          {input && (
            <button
              onClick={() => { setInput(''); onSearch('') }}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
              aria-label="Исчисти пребарување"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>

        {/* Stats pills */}
        {stats && (
          <div className="hidden md:flex items-center gap-2 text-xs font-mono">
            <span className="px-2.5 py-1 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400">
              {stats.total.toLocaleString()} огласи
            </span>
            <span className="px-2.5 py-1 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400">
              {stats.duplicates.toLocaleString()} дубликати
            </span>
            {stats.good_deals > 0 && (
              <span className="px-2.5 py-1 rounded-full bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400">
                {stats.good_deals.toLocaleString()} добри цени
              </span>
            )}
          </div>
        )}

        {/* Wishlist button */}
        <button
          onClick={onWishlistOpen}
          className="btn-ghost relative"
          aria-label="Листа на желби"
        >
          <svg className={`w-4 h-4 transition-colors ${wishlistCount > 0 ? 'text-red-400' : ''}`} fill={wishlistCount > 0 ? 'currentColor' : 'none'} viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
          </svg>
          {wishlistCount > 0 && (
            <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center leading-none">
              {wishlistCount > 9 ? '9+' : wishlistCount}
            </span>
          )}
        </button>

        {/* Theme toggle */}
        <button
          onClick={onThemeToggle}
          className="btn-ghost ml-auto"
          aria-label="Промени тема"
        >
          {theme === 'dark' ? (
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364-6.364l-.707.707M6.343 17.657l-.707.707M17.657 17.657l-.707-.707M6.343 6.343l-.707-.707M12 6a6 6 0 100 12 6 6 0 000-12z" />
            </svg>
          ) : (
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
            </svg>
          )}
        </button>
      </div>
    </header>
  )
}
