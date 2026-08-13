import { useState, useEffect, useCallback } from 'react'
import Header from './components/Header'
import Sidebar from './components/Sidebar'
import AdGrid from './components/AdGrid'
import AdModal from './components/AdModal'
import WishlistPanel from './components/WishlistPanel'
import Footer from './components/Footer'
import AnalyticsPage from './pages/AnalyticsPage'
import { useWishlist } from './hooks/useWishlist'
import { fetchAds, fetchStats, fetchCategories } from './api/client'

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

export default function App() {
  const [page, setPage] = useState('ads')
  const [theme, setTheme] = useState(
    () => localStorage.getItem('theme') || 'dark'
  )
  const [filters, setFilters] = useState(INITIAL_FILTERS)
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
      />

      <div className="flex flex-1 overflow-hidden">
        {page === 'ads' && (
          <Sidebar
            filters={filters}
            stats={stats}
            categories={categories}
            onChange={update}
            onClear={clearFilters}
          />
        )}

        <main className="flex-1 overflow-y-auto">
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
            onPageChange={p => setFilters(prev => ({ ...prev, page: p }))}
            onAdClick={setSelectedAd}
            isSaved={isSaved}
            onWishlistToggle={toggleWishlist}
          />}

          <Footer
            categories={categories}
            onCategoryClick={name => { update('category', name); setPage('ads') }}
            onNavigate={setPage}
          />
        </main>
      </div>

      {selectedAd && (
        <AdModal
          ad={selectedAd}
          onClose={() => setSelectedAd(null)}
          isSaved={isSaved}
          onWishlistToggle={toggleWishlist}
        />
      )}

      {wishlistOpen && (
        <WishlistPanel
          wishlist={wishlist}
          onToggle={toggleWishlist}
          onClose={() => setWishlistOpen(false)}
          onAdClick={ad => { setSelectedAd(ad); setWishlistOpen(false) }}
        />
      )}
    </div>
  )
}
