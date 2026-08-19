import { useEffect, useState } from 'react'
import { fetchAdsBatch } from '../api/client'

const CONDITION_LABELS = {
  new: 'Нов', like_new: 'Како нов', used: 'Користен', for_parts: 'За делови',
}

function WishlistCard({ ad, onRemove, onClick }) {
  const images = Array.isArray(ad.images) ? ad.images : []
  const img = images[0]

  return (
    <div className="flex items-center gap-3 p-2 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-800/60 group transition-colors">
      {/* Thumbnail */}
      <button
        onClick={() => onClick(ad)}
        className="w-14 h-14 shrink-0 rounded-lg overflow-hidden bg-slate-100 dark:bg-slate-800"
      >
        {img ? (
          <img src={img} alt="" className="w-full h-full object-contain" onError={e => { e.target.style.display = 'none' }} />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <svg className="w-5 h-5 text-slate-300 dark:text-slate-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
          </div>
        )}
      </button>

      {/* Info */}
      <button onClick={() => onClick(ad)} className="flex-1 min-w-0 text-left">
        <p className="text-sm font-medium text-slate-900 dark:text-slate-100 line-clamp-2 leading-snug">
          {ad.title}
        </p>
        <div className="flex items-center gap-2 mt-0.5">
          {ad.price_eur ? (
            <span className="text-sm font-bold text-violet-600 dark:text-violet-400 font-mono">
              {Number(ad.price_eur).toLocaleString('mk-MK')} €
            </span>
          ) : (
            <span className="text-xs text-slate-400">По договор</span>
          )}
          {ad.condition && (
            <span className="text-[10px] text-slate-400 dark:text-slate-500">
              {CONDITION_LABELS[ad.condition] || ad.condition}
            </span>
          )}
        </div>
      </button>

      {/* Remove */}
      <button
        onClick={() => onRemove(ad)}
        className="shrink-0 p-1.5 rounded-lg text-slate-300 dark:text-slate-600 hover:text-red-400 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors opacity-0 group-hover:opacity-100"
        aria-label="Отстрани"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  )
}

export default function WishlistPanel({ wishlistUrls, onToggle, onClose, onAdClick }) {
  const [ads, setAds] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const onKey = e => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  // Fetch live data for the saved ad_urls on every open — prices/condition/
  // images can change or an ad can be pulled entirely, so the panel should
  // never show a frozen save-time snapshot.
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetchAdsBatch(wishlistUrls)
      .then(fetched => {
        if (cancelled) return
        // Preserve save-order (most-recently-added first) — the batch
        // endpoint doesn't guarantee it. Drop any ad that's since vanished
        // from the DB entirely rather than showing a broken entry.
        const byUrl = new Map(fetched.map(a => [a.ad_url, a]))
        setAds(wishlistUrls.map(u => byUrl.get(u)).filter(Boolean))
      })
      .catch(() => { if (!cancelled) setAds([]) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [wishlistUrls])

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Drawer */}
      <aside className="fixed right-0 top-0 bottom-0 z-50 w-80 bg-white dark:bg-slate-900 border-l border-slate-200 dark:border-slate-800 shadow-2xl flex flex-col animate-slideUp">

        {/* Header */}
        <div className="flex items-center justify-between px-4 py-4 border-b border-slate-100 dark:border-slate-800 shrink-0">
          <div className="flex items-center gap-2">
            <svg className="w-5 h-5 text-red-400" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" />
            </svg>
            <h2 className="font-semibold text-slate-900 dark:text-slate-100">
              Листа на желби
            </h2>
            {wishlistUrls.length > 0 && (
              <span className="text-xs font-mono bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 px-1.5 py-0.5 rounded-full">
                {wishlistUrls.length}
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto p-3">
          {wishlistUrls.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center py-16 gap-3">
              <svg className="w-12 h-12 text-slate-200 dark:text-slate-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
              </svg>
              <p className="text-sm text-slate-400 dark:text-slate-500 font-medium">
                Нема зачувани огласи
              </p>
              <p className="text-xs text-slate-300 dark:text-slate-600">
                Кликни на срцето на некој оглас за да го зачуваш
              </p>
            </div>
          ) : loading ? (
            <div className="space-y-1 animate-pulse">
              {wishlistUrls.map(u => (
                <div key={u} className="flex items-center gap-3 p-2">
                  <div className="w-14 h-14 shrink-0 rounded-lg bg-slate-100 dark:bg-slate-800" />
                  <div className="flex-1 space-y-2">
                    <div className="h-3 w-3/4 rounded bg-slate-100 dark:bg-slate-800" />
                    <div className="h-3 w-1/3 rounded bg-slate-100 dark:bg-slate-800" />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="space-y-1">
              {ads.map(ad => (
                <WishlistCard
                  key={ad.ad_url}
                  ad={ad}
                  onRemove={onToggle}
                  onClick={ad => { onAdClick(ad); onClose() }}
                />
              ))}
            </div>
          )}
        </div>

        {/* Footer — clear all */}
        {wishlistUrls.length > 0 && (
          <div className="shrink-0 p-3 border-t border-slate-100 dark:border-slate-800">
            <button
              onClick={() => wishlistUrls.forEach(u => onToggle(u))}
              className="w-full py-2 rounded-lg text-sm text-slate-400 dark:text-slate-500 hover:text-red-400 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
            >
              Исчисти ги сите
            </button>
          </div>
        )}
      </aside>
    </>
  )
}
