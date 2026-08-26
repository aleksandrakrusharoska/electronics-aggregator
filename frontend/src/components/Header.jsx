import { useState, useEffect, useRef } from 'react'
import { fetchSuggestions } from '../api/client'
import logo from '../assets/logo.png'

export default function Header({ stats, theme, onThemeToggle, q, onSearch, wishlistCount, onWishlistOpen, page, onPageChange, onLogoClick }) {
  const [input, setInput] = useState(q || '')
  const [suggestions, setSuggestions] = useState([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const timerRef = useRef(null)
  const suggestTimerRef = useRef(null)
  const requestIdRef = useRef(0)

  useEffect(() => {
    setInput(q || '')
  }, [q])

  const fetchSuggestionsFor = val => {
    clearTimeout(suggestTimerRef.current)
    if (val.trim().length < 2) {
      setSuggestions([])
      setShowSuggestions(false)
      return
    }
    suggestTimerRef.current = setTimeout(async () => {
      const requestId = ++requestIdRef.current
      const results = await fetchSuggestions(val.trim())
      if (requestId !== requestIdRef.current) return // a newer keystroke already superseded this request
      setSuggestions(results)
      setShowSuggestions(results.length > 0)
      setActiveIndex(-1)
    }, 200)
  }

  const handleChange = e => {
    const val = e.target.value
    setInput(val)
    clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => onSearch(val), 350)
    fetchSuggestionsFor(val)
  }

  const selectSuggestion = title => {
    setInput(title)
    onSearch(title)
    setSuggestions([])
    setShowSuggestions(false)
    setActiveIndex(-1)
    clearTimeout(timerRef.current)
    clearTimeout(suggestTimerRef.current)
  }

  const handleKey = e => {
    if (e.key === 'ArrowDown' && showSuggestions) {
      e.preventDefault()
      setActiveIndex(i => (i + 1) % suggestions.length)
      return
    }
    if (e.key === 'ArrowUp' && showSuggestions) {
      e.preventDefault()
      setActiveIndex(i => (i - 1 + suggestions.length) % suggestions.length)
      return
    }
    if (e.key === 'Enter') {
      if (showSuggestions && activeIndex >= 0) {
        selectSuggestion(suggestions[activeIndex].title)
        return
      }
      clearTimeout(timerRef.current)
      setShowSuggestions(false)
      onSearch(input)
    }
    if (e.key === 'Escape') {
      if (showSuggestions) {
        setShowSuggestions(false)
        return
      }
      setInput('')
      clearTimeout(timerRef.current)
      onSearch('')
    }
  }

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200 dark:border-slate-800 bg-white/90 dark:bg-slate-950/90 backdrop-blur-md">
      <div className="flex items-center gap-4 px-6 h-14">

        {/* Logo */}
        <button onClick={onLogoClick} className="flex items-center gap-2 shrink-0" aria-label="Почетна">
          <img src={logo} alt="ElectroFlow" className="w-7 h-7 rounded-lg object-cover" />
          <div className="leading-tight">
            <div className="font-semibold text-sm tracking-tight text-slate-900 dark:text-slate-100">
              Electro<span className="text-violet-500 dark:text-violet-400">Flow</span>
            </div>
          </div>
        </button>

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
            onFocus={() => { if (suggestions.length > 0) setShowSuggestions(true) }}
            onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
            role="combobox"
            aria-expanded={showSuggestions}
            aria-autocomplete="list"
          />
          {input && (
            <button
              onClick={() => { setInput(''); onSearch(''); setSuggestions([]); setShowSuggestions(false) }}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
              aria-label="Исчисти пребарување"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}

          {showSuggestions && (
            <ul className="absolute left-0 right-0 top-full mt-1.5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-lg shadow-black/5 dark:shadow-black/30 overflow-hidden z-50 max-h-96 overflow-y-auto">
              {suggestions.map((s, i) => (
                <li key={s.ad_url}>
                  <button
                    onMouseDown={e => { e.preventDefault(); selectSuggestion(s.title) }}
                    onMouseEnter={() => setActiveIndex(i)}
                    className={`w-full flex items-center gap-3 px-3 py-2 text-left transition-colors ${
                      i === activeIndex ? 'bg-violet-50 dark:bg-violet-900/20' : 'hover:bg-slate-50 dark:hover:bg-slate-800/60'
                    }`}
                  >
                    <div className="w-9 h-9 shrink-0 rounded-lg overflow-hidden bg-slate-100 dark:bg-slate-800 flex items-center justify-center">
                      {s.image ? (
                        <img src={s.image} alt="" className="w-full h-full object-contain" onError={e => { e.target.style.display = 'none' }} />
                      ) : (
                        <svg className="w-4 h-4 text-slate-300 dark:text-slate-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                        </svg>
                      )}
                    </div>
                    <span className="flex-1 min-w-0 text-sm text-slate-700 dark:text-slate-300 truncate">{s.title}</span>
                    {s.price_eur != null && (
                      <span className="shrink-0 text-xs font-mono font-semibold text-violet-600 dark:text-violet-400">
                        {Number(s.price_eur).toLocaleString('mk-MK')} €
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Stats pills */}
        {stats && (
          <div className="hidden md:flex items-center gap-2 text-xs font-mono">
            <span className="px-2.5 py-1 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400">
              {stats.total.toLocaleString()} огласи
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
