import { useState, useEffect, useCallback } from 'react'
import Header from './components/Header'
import Sidebar from './components/Sidebar'
import AdGrid from './components/AdGrid'
import AdModal from './components/AdModal'
import WishlistPanel from './components/WishlistPanel'
import Footer from './components/Footer'
import AnalyticsPage from './pages/AnalyticsPage'
import LandingPage from './pages/LandingPage'
import { useWishlist } from './hooks/useWishlist'
import { fetchAds, fetchStats, fetchCategories, fetchAdDetail } from './api/client'

const INITIAL_FILTERS = {
  source: '',
  category: '',
  condition: '',
  min_price: '',
  max_price: '',
  q: '',
  sort: 'newest',
  good_deal_only: false,
  ad_type: 'product',
  page: 1,
}

const FILTER_KEYS = Object.keys(INITIAL_FILTERS)

// Filters/page/view/ad-open state all live in the URL query string so a
// search, a specific page, or an open ad can be shared/bookmarked and
// survive a refresh — none of that worked before (pure React state only).
function parseFiltersFromParams(params) {
  const filters = { ...INITIAL_FILTERS }
  for (const key of FILTER_KEYS) {
    if (!params.has(key)) continue
    const raw = params.get(key)
    if (key === 'page') filters.page = Math.max(1, parseInt(raw, 10) || 1)
    else if (key === 'good_deal_only') filters.good_deal_only = raw === 'true'
    else filters[key] = raw
  }
  return filters
}

function parseViewFromParams(params) {
  const view = params.get('view')
  if (view === 'analytics') return 'analytics'
  if (view === 'ads') return 'ads'
  return 'landing'
}

// Read-modify-write against the *current* URL so this can update just its
// own slice (filters, or the `ad` param) without clobbering the other.
function updateUrl(mutate, { push = false, state } = {}) {
  const params = new URLSearchParams(window.location.search)
  mutate(params)
  const qs = params.toString()
  const url = qs ? `${window.location.pathname}?${qs}` : window.location.pathname
  if (push) window.history.pushState(state ?? null, '', url)
  else window.history.replaceState(state !== undefined ? state : window.history.state, '', url)
}

export default function App() {
  const [initialParams] = useState(() => new URLSearchParams(window.location.search))
  const [page, setPage] = useState(() => parseViewFromParams(initialParams))
  const [theme, setTheme] = useState(
    () => localStorage.getItem('theme') || 'dark'
  )
  const [filters, setFilters] = useState(() => parseFiltersFromParams(initialParams))
  const [ads, setAds] = useState([])
  const [total, setTotal] = useState(0)
  const [pages, setPages] = useState(1)
  const [stats, setStats] = useState(null)
  const [categories, setCategories] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selectedAd, setSelectedAd] = useState(null)
  const [wishlistOpen, setWishlistOpen] = useState(false)
  const { wishlist, toggle: toggleWishlist, isSaved } = useWishlist()

  // Restore a deep-linked ad (?ad=<url>) on first load — it may not be in
  // whatever page of results the current filters would return, so it's
  // fetched directly rather than searched for in `ads`.
  useEffect(() => {
    const adUrl = initialParams.get('ad')
    if (!adUrl) return
    fetchAdDetail(adUrl).then(a => { if (a) setSelectedAd(a) }).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Keep filters/page/view in the URL (replaceState — these change too
  // often, e.g. every filter click, to each get their own history entry).
  useEffect(() => {
    updateUrl(params => {
      for (const key of FILTER_KEYS) {
        const value = filters[key]
        if (value === INITIAL_FILTERS[key] || value === '' || value == null) params.delete(key)
        else params.set(key, value)
      }
      if (page === 'analytics' || page === 'ads') params.set('view', page)
      else params.delete('view')
    })
  }, [filters, page])

  // Opening an ad *does* get its own history entry, so the back button
  // closes the modal the way users expect a detail overlay to behave.
  const openAd = useCallback(ad => {
    setSelectedAd(ad)
    updateUrl(params => params.set('ad', ad.ad_url), { push: true, state: { adOpened: true } })
  }, [])

  // Browsing "similar ads" inside an already-open modal updates the URL
  // (so the address bar/share link stays accurate) without stacking a new
  // history entry per click.
  const navigateAd = useCallback(ad => {
    setSelectedAd(ad)
    updateUrl(params => params.set('ad', ad.ad_url))
  }, [])

  const closeAd = useCallback(() => {
    if (window.history.state?.adOpened) {
      window.history.back()
    } else {
      // Landed here via a shared ?ad= link (no history entry we pushed) —
      // nothing to go back to, just drop the param.
      setSelectedAd(null)
      updateUrl(params => params.delete('ad'))
    }
  }, [])

  // Back/forward navigation: re-sync all state from wherever the URL now
  // points, including re-opening or closing the ad modal to match.
  useEffect(() => {
    function onPopState() {
      const params = new URLSearchParams(window.location.search)
      setFilters(parseFiltersFromParams(params))
      setPage(parseViewFromParams(params))
      const adUrl = params.get('ad')
      if (!adUrl) {
        setSelectedAd(null)
        return
      }
      setSelectedAd(prev => {
        if (prev && prev.ad_url === adUrl) return prev
        fetchAdDetail(adUrl).then(a => { if (a) setSelectedAd(a) }).catch(() => {})
        return prev
      })
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  useEffect(() => {
    const root = document.documentElement
    if (theme === 'dark') root.classList.add('dark')
    else root.classList.remove('dark')
    localStorage.setItem('theme', theme)
  }, [theme])

  useEffect(() => {
    fetchStats().then(setStats).catch(() => {})
    fetchCategories().then(setCategories).catch(() => {})
  }, [])

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchAds(filters)
      .then(data => {
        setAds(data.items || [])
        setTotal(data.total || 0)
        setPages(data.pages || 1)
      })
      .catch(() => setError('fetch_failed'))
      .finally(() => setLoading(false))
  }, [filters])

  const update = useCallback((key, value) => {
    setFilters(prev => ({ ...prev, [key]: value, page: 1 }))
  }, [])

  const clearFilters = useCallback(() => {
    setFilters(INITIAL_FILTERS)
  }, [])

  if (page === 'landing') {
    return (
      <LandingPage
        stats={stats}
        categories={categories}
        onEnter={() => setPage('ads')}
        onAnalytics={() => setPage('analytics')}
        onCategoryClick={name => { update('category', name); setPage('ads') }}
      />
    )
  }

  return (
    <div className="min-h-screen flex flex-col">
      <Header
        stats={stats}
        theme={theme}
        onThemeToggle={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}
        q={filters.q}
        onSearch={q => update('q', q)}
        wishlistCount={wishlist.length}
        onWishlistOpen={() => setWishlistOpen(true)}
        page={page}
        onPageChange={setPage}
        onLogoClick={() => setPage('landing')}
      />

      <div className="flex flex-1">
        {page === 'ads' && (
          <Sidebar
            filters={filters}
            stats={stats}
            categories={categories}
            onChange={update}
            onClear={clearFilters}
          />
        )}

        <main className="flex-1 min-w-0">
          {page === 'analytics' && <AnalyticsPage theme={theme} />}
          {page === 'ads' && error && (
            <div className="mx-6 mt-6 flex items-start gap-3 p-4 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-100 dark:border-red-800">
              <svg className="w-5 h-5 text-red-500 dark:text-red-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-red-700 dark:text-red-300">Огласите моментално не се достапни</p>
                <p className="text-xs text-red-500 dark:text-red-400 mt-0.5">
                  Обиди се повторно за малку. Ако проблемот продолжува, можно е сервисот да е привремено недостапен.
                </p>
              </div>
              <button onClick={() => setError(null)} className="shrink-0 text-red-400 hover:text-red-600 dark:hover:text-red-300">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          )}
          {page === 'ads' && <AdGrid
            ads={ads}
            total={total}
            loading={loading}
            page={filters.page}
            pages={pages}
            adType={filters.ad_type}
            onPageChange={p => setFilters(prev => ({ ...prev, page: p }))}
            onAdClick={openAd}
            isSaved={isSaved}
            onWishlistToggle={toggleWishlist}
          />}
        </main>
      </div>

      <Footer
        categories={categories}
        onCategoryClick={name => { update('category', name); setPage('ads') }}
        onNavigate={setPage}
      />

      {selectedAd && (
        <AdModal
          ad={selectedAd}
          onClose={closeAd}
          onNavigate={navigateAd}
          isSaved={isSaved}
          onWishlistToggle={toggleWishlist}
        />
      )}

      {wishlistOpen && (
        <WishlistPanel
          wishlistUrls={wishlist}
          onToggle={toggleWishlist}
          onClose={() => setWishlistOpen(false)}
          onAdClick={ad => { openAd(ad); setWishlistOpen(false) }}
        />
      )}
    </div>
  )
}
