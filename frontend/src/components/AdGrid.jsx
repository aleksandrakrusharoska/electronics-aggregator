import { useState } from 'react'
import AdCard from './AdCard'
import { formatDate } from '../utils/formatDate'
import { inferSource } from '../utils/inferSource'

const CONDITION_LABELS = {
  'New':             'Нов',
  'Used - Like New': 'Како нов',
  'Used - Good':     'Добра состојба',
  'Used - Fair':     'Солидна состојба',
  'Used':            'Користен',
  'For parts':       'За делови',
}

function SkeletonCard() {
  return (
    <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-100 dark:border-slate-800 overflow-hidden animate-pulse">
      <div className="aspect-[4/3] bg-slate-100 dark:bg-slate-800" />
      <div className="p-3 space-y-2">
        <div className="h-3 w-16 bg-slate-100 dark:bg-slate-800 rounded" />
        <div className="h-4 w-full bg-slate-100 dark:bg-slate-800 rounded" />
        <div className="h-4 w-3/4 bg-slate-100 dark:bg-slate-800 rounded" />
        <div className="h-5 w-24 bg-slate-100 dark:bg-slate-800 rounded" />
      </div>
    </div>
  )
}

function SkeletonRow() {
  return (
    <div className="flex items-center gap-4 p-3 bg-white dark:bg-slate-900 rounded-xl border border-slate-100 dark:border-slate-800 animate-pulse">
      <div className="w-16 h-16 shrink-0 rounded-lg bg-slate-100 dark:bg-slate-800" />
      <div className="flex-1 space-y-2 min-w-0">
        <div className="h-4 w-3/4 bg-slate-100 dark:bg-slate-800 rounded" />
        <div className="h-3 w-1/3 bg-slate-100 dark:bg-slate-800 rounded" />
      </div>
      <div className="h-5 w-20 bg-slate-100 dark:bg-slate-800 rounded shrink-0" />
    </div>
  )
}

function AdRow({ ad, onClick }) {
  const images = Array.isArray(ad.images) ? ad.images : (ad.image_url ? [ad.image_url] : [])
  const img = images[0]
  const source = inferSource(ad)
  const isGoodDeal = ad.good_price_deal
  const isOverpriced = ad.price_vs_new_ratio > 1

  return (
    <article
      onClick={() => onClick(ad)}
      className="group flex items-center gap-3 p-3 bg-white dark:bg-slate-900 rounded-xl border border-slate-100 dark:border-slate-800 cursor-pointer hover:border-violet-300 dark:hover:border-violet-700 hover:shadow-md hover:shadow-violet-500/5 transition-all duration-150 animate-fadeIn"
    >
      {/* Thumbnail */}
      <div className="w-16 h-16 shrink-0 rounded-lg overflow-hidden bg-slate-100 dark:bg-slate-800">
        {img ? (
          <img src={img} alt="" className="w-full h-full object-contain group-hover:scale-105 transition-transform duration-300" onError={e => { e.target.style.display = 'none' }} />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <svg className="w-6 h-6 text-slate-300 dark:text-slate-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
          </div>
        )}
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 mb-1 flex-wrap">
          {source && (
            <span className={`text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded ${
              source === 'reklama5'
                ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
                : 'bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300'
            }`}>
              {source}
            </span>
          )}
          {ad.condition && (
            <span className="text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400">
              {CONDITION_LABELS[ad.condition] || ad.condition}
            </span>
          )}
          {isGoodDeal && (
            <span className="text-[10px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400">
              Добра цена
            </span>
          )}
          {!isGoodDeal && isOverpriced && (
            <span className="text-[10px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400">
              Прескапо
            </span>
          )}
          {ad.ad_type === 'service' && (
            <span className="text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300">Услуга</span>
          )}
          {ad.ad_type === 'wanted' && (
            <span className="text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-sky-100 dark:bg-sky-900/30 text-sky-700 dark:text-sky-300">Барање</span>
          )}
        </div>
        <h3 className="text-sm font-medium text-slate-900 dark:text-slate-100 truncate">{ad.title}</h3>
        {ad.location && (
          <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-0.5 flex items-center gap-1">
            <svg className="w-3 h-3 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
            </svg>
            {ad.location}
          </p>
        )}
      </div>

      {/* Price + date */}
      <div className="shrink-0 text-right">
        {ad.price_eur ? (
          <div className="text-base font-bold text-violet-600 dark:text-violet-400 font-mono">
            {Number(ad.price_eur).toLocaleString('mk-MK')} €
          </div>
        ) : (
          <div className="text-sm text-slate-400 dark:text-slate-500">По договор</div>
        )}
        {(ad.posted_date || ad.scraped_at) && (
          <div className="text-[11px] text-slate-400 dark:text-slate-600 font-mono mt-0.5">
            {formatDate(ad.posted_date || ad.scraped_at)}
          </div>
        )}
      </div>
    </article>
  )
}

function Pagination({ page, pages, onChange }) {
  if (pages <= 1) return null

  const getPages = () => {
    const arr = []
    const delta = 2
    for (let i = Math.max(1, page - delta); i <= Math.min(pages, page + delta); i++) {
      arr.push(i)
    }
    return arr
  }

  return (
    <nav className="flex items-center justify-center gap-1 py-8" aria-label="Pagination">
      <button
        onClick={() => onChange(page - 1)}
        disabled={page === 1}
        className="px-3 py-1.5 rounded-lg text-sm text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
      >
        ←
      </button>

      {getPages()[0] > 1 && (
        <>
          <button onClick={() => onChange(1)} className="px-3 py-1.5 rounded-lg text-sm text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors">1</button>
          {getPages()[0] > 2 && <span className="px-1 text-slate-400">…</span>}
        </>
      )}

      {getPages().map(p => (
        <button
          key={p}
          onClick={() => onChange(p)}
          className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
            p === page
              ? 'bg-violet-600 text-white font-medium'
              : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
          }`}
        >
          {p}
        </button>
      ))}

      {getPages().at(-1) < pages && (
        <>
          {getPages().at(-1) < pages - 1 && <span className="px-1 text-slate-400">…</span>}
          <button onClick={() => onChange(pages)} className="px-3 py-1.5 rounded-lg text-sm text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors">{pages}</button>
        </>
      )}

      <button
        onClick={() => onChange(page + 1)}
        disabled={page === pages}
        className="px-3 py-1.5 rounded-lg text-sm text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
      >
        →
      </button>
    </nav>
  )
}

export default function AdGrid({ ads, total, loading, page, pages, onPageChange, onAdClick, isSaved, onWishlistToggle }) {
  const [viewMode, setViewMode] = useState('grid')

  if (!loading && ads.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-32 text-center">
        <svg className="w-16 h-16 text-slate-200 dark:text-slate-800 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <p className="text-slate-400 dark:text-slate-500 font-medium">Нема пронајдени огласи</p>
        <p className="text-sm text-slate-300 dark:text-slate-600 mt-1">Пробај со поинакви филтри</p>
      </div>
    )
  }

  return (
    <div className="p-6">
      {/* Toolbar */}
      <div className="flex items-center justify-between mb-4">
        {!loading && total > 0 ? (
          <p className="text-sm text-slate-400 dark:text-slate-500 font-mono">
            {total.toLocaleString()} огласи
          </p>
        ) : (
          <div />
        )}

        {/* View toggle */}
        <div className="flex items-center gap-0.5 p-0.5 bg-slate-100 dark:bg-slate-800 rounded-lg">
          <button
            onClick={() => setViewMode('grid')}
            aria-label="Решетка"
            className={`p-1.5 rounded-md transition-colors ${
              viewMode === 'grid'
                ? 'bg-white dark:bg-slate-700 text-slate-700 dark:text-slate-200 shadow-sm'
                : 'text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300'
            }`}
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
            </svg>
          </button>
          <button
            onClick={() => setViewMode('list')}
            aria-label="Листа"
            className={`p-1.5 rounded-md transition-colors ${
              viewMode === 'list'
                ? 'bg-white dark:bg-slate-700 text-slate-700 dark:text-slate-200 shadow-sm'
                : 'text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300'
            }`}
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 10h16M4 14h16M4 18h16" />
            </svg>
          </button>
        </div>
      </div>

      {/* Content */}
      {viewMode === 'grid' ? (
        <div className="grid grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-4">
          {loading
            ? Array.from({ length: 24 }).map((_, i) => <SkeletonCard key={i} />)
            : ads.map(ad => (
                <AdCard key={ad.ad_url} ad={ad} onClick={onAdClick} isSaved={isSaved?.(ad.ad_url)} onWishlistToggle={onWishlistToggle} />
              ))
          }
        </div>
      ) : (
        <div className="space-y-2">
          {loading
            ? Array.from({ length: 24 }).map((_, i) => <SkeletonRow key={i} />)
            : ads.map(ad => (
                <AdRow key={ad.ad_url} ad={ad} onClick={onAdClick} />
              ))
          }
        </div>
      )}

      <Pagination page={page} pages={pages} onChange={onPageChange} />
    </div>
  )
}
