import { useState } from 'react'
import AdCard from './AdCard'
import { formatDate } from '../utils/formatDate'
import { firstRealImage } from '../utils/images'
import { formatEur } from '../utils/formatPrice'
import { formatTitle } from '../utils/formatTitle'
import ConditionTag from './ConditionTag'
import SourceTag from './SourceTag'
import PriceBadge from './PriceBadge'

const AD_TYPE_BORDER_CLS = {
  service: 'border-amber-200 dark:border-amber-800 hover:border-amber-400 dark:hover:border-amber-600 hover:shadow-amber-500/10',
  wanted:  'border-emerald-200 dark:border-emerald-800 hover:border-emerald-400 dark:hover:border-emerald-600 hover:shadow-emerald-500/10',
}
const DEFAULT_BORDER_CLS = 'border-violet-200 dark:border-violet-800 hover:border-violet-400 dark:hover:border-violet-600 hover:shadow-violet-500/10'

const AD_TYPE_PRICE_CLS = {
  service: 'text-amber-700 dark:text-amber-300',
  wanted:  'text-emerald-700 dark:text-emerald-300',
}
const DEFAULT_PRICE_CLS = 'text-violet-600 dark:text-violet-400'

const AD_TYPE_PAGE_CLS = {
  service: 'bg-amber-500',
  wanted:  'bg-emerald-600',
}
const DEFAULT_PAGE_CLS = 'bg-violet-600'

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
  const img = firstRealImage(images)
  const borderCls = AD_TYPE_BORDER_CLS[ad.ad_type] || DEFAULT_BORDER_CLS
  const priceCls = AD_TYPE_PRICE_CLS[ad.ad_type] || DEFAULT_PRICE_CLS

  return (
    <article
      onClick={() => onClick(ad)}
      className={`group flex items-center gap-3 p-3 bg-white dark:bg-slate-900 rounded-xl border cursor-pointer hover:shadow-md transition-all duration-150 animate-fadeIn ${borderCls}`}
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

      {/* Info: same tags, badge, title and location · date as the grid card */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1 flex-wrap text-xs">
          <SourceTag ad={ad} />
          <ConditionTag condition={ad.condition} />
          <PriceBadge ad={ad} />
          {ad.delivery_available && <span className="font-medium text-slate-500 dark:text-slate-400">· Достава</span>}
        </div>
        <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100 truncate">{formatTitle(ad.title)}</h3>
        {(ad.location || ad.posted_date || ad.scraped_at) && (
          <p className="text-[11px] font-medium text-slate-500 dark:text-slate-400 mt-0.5 flex items-center gap-0.5 min-w-0">
            {ad.location && (
              <>
                <svg className="w-3.5 h-3.5 shrink-0 text-red-600" viewBox="0 0 24 24">
                  <path fill="currentColor" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                  <circle cx="12" cy="10.5" r="2.75" className="fill-white dark:fill-slate-900" />
                </svg>
                <span className="truncate">{ad.location}</span>
              </>
            )}
            {ad.location && (ad.posted_date || ad.scraped_at) && <span className="shrink-0 px-0.5">·</span>}
            {(ad.posted_date || ad.scraped_at) && (
              <span className="shrink-0">{formatDate(ad.posted_date || ad.scraped_at)}</span>
            )}
          </p>
        )}
      </div>

      {/* Price */}
      <div className="shrink-0 text-right">
        {ad.price_eur ? (
          <div className={`text-base font-bold ${priceCls}`}>
            {formatEur(ad.price_eur)}
          </div>
        ) : (
          <div className="text-sm font-medium text-slate-500 dark:text-slate-400">По договор</div>
        )}
      </div>
    </article>
  )
}

function Pagination({ page, pages, onChange, adType }) {
  const [jump, setJump] = useState('')
  if (pages <= 1) return null

  // "Оди на страница": type a number, Enter (or the arrow) goes there
  const goTo = () => {
    const n = parseInt(jump, 10)
    if (!Number.isNaN(n)) onChange(Math.min(pages, Math.max(1, n)))
    setJump('')
  }

  const pageCls = AD_TYPE_PAGE_CLS[adType] || DEFAULT_PAGE_CLS

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
              ? `${pageCls} text-white font-medium`
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

      <form
        className="flex items-center gap-1.5 ml-4 text-sm text-slate-500 dark:text-slate-400"
        onSubmit={e => { e.preventDefault(); goTo() }}
      >
        <label htmlFor="page-jump">Страница</label>
        <input
          id="page-jump"
          type="number"
          min={1}
          max={pages}
          value={jump}
          onChange={e => setJump(e.target.value)}
          placeholder={String(page)}
          className="w-16 px-2 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-200 text-sm text-center focus:outline-none focus:ring-2 focus:ring-violet-500/40 [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
        />
        <span>од {pages.toLocaleString('mk-MK')}</span>
        <button
          type="submit"
          className="px-2.5 py-1.5 rounded-lg text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          aria-label="Одете на страницата"
        >
          Оди
        </button>
      </form>
    </nav>
  )
}

const SORTS = [
  { value: 'newest',     label: 'Најнови' },
  { value: 'price_asc',  label: 'Најевтини' },
  { value: 'price_desc', label: 'Најскапи' },
  // only offered with "Добри цени" on (the backend applies that filter for it too)
  { value: 'best_deal',  label: 'Најголем попуст', goodDealsOnly: true },
]

export default function AdGrid({ ads, total, loading, page, pages, adType, sort, goodDealOnly, onSortChange, onPageChange, onAdClick, isSaved, onWishlistToggle }) {
  const [viewMode, setViewMode] = useState('grid')

  if (!loading && ads.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-32 text-center">
        <svg className="w-16 h-16 text-slate-200 dark:text-slate-800 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <p className="text-slate-400 dark:text-slate-500 font-medium">Нема пронајдени огласи</p>
        <p className="text-sm text-slate-300 dark:text-slate-600 mt-1">Пробајте со поинакви филтри</p>
      </div>
    )
  }

  return (
    <div className="pl-6 pr-14 py-6">
      {/* Toolbar: count on the left; sort and grid/list toggle on the right */}
      <div className="flex items-center justify-between gap-3 mb-4">
        {!loading && total > 0 ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">
            {total.toLocaleString('mk-MK')} огласи
          </p>
        ) : (
          <div />
        )}

        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
            Подреди по
            <select
              value={sort}
              onChange={e => onSortChange(e.target.value)}
              className="py-1.5 pl-2.5 pr-8 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500/40"
            >
              {SORTS.filter(s => !s.goodDealsOnly || goodDealOnly).map(s => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
          </label>

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
      </div>

      {/* Content */}
      {viewMode === 'grid' ? (
        <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {loading
            ? Array.from({ length: 16 }).map((_, i) => <SkeletonCard key={i} />)
            : ads.map(ad => (
                <AdCard key={ad.ad_url} ad={ad} onClick={onAdClick} isSaved={isSaved?.(ad.ad_url)} onWishlistToggle={onWishlistToggle} />
              ))
          }
        </div>
      ) : (
        <div className="space-y-2">
          {loading
            ? Array.from({ length: 16 }).map((_, i) => <SkeletonRow key={i} />)
            : ads.map(ad => (
                <AdRow key={ad.ad_url} ad={ad} onClick={onAdClick} />
              ))
          }
        </div>
      )}

      <Pagination page={page} pages={pages} onChange={onPageChange} adType={adType} />
    </div>
  )
}
