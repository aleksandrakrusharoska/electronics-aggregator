import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { formatDate } from '../utils/formatDate'
import { inferSource, sourceLabel } from '../utils/inferSource'
import { formatTitle } from '../utils/formatTitle'
import { firstRealImage } from '../utils/images'

const AD_TYPE_ACCENT = {
  service: { price: 'text-amber-700 dark:text-amber-300' },
  wanted:  { price: 'text-emerald-700 dark:text-emerald-300' },
}
const DEFAULT_ACCENT = { price: 'text-violet-600 dark:text-violet-400' }

const CONDITION_LABELS = {
  'New':             { label: 'Нов' },
  'Used - Like New': { label: 'Како нов' },
  'Used - Good':     { label: 'Добра состојба' },
  'Used - Fair':     { label: 'Солидна состојба' },
  'Used':            { label: 'Користен' },
  'For parts':       { label: 'За делови' },
}

export default function AdCard({ ad, onClick, isSaved, onWishlistToggle }) {
  const images = Array.isArray(ad.images) ? ad.images : (ad.image_url ? [ad.image_url] : [])
  const img = firstRealImage(images)
  const cond = CONDITION_LABELS[ad.condition]
  const source = inferSource(ad)
  const tags = [source && sourceLabel(source), cond?.label, ad.delivery_available && 'Достава'].filter(Boolean)

  const isGoodDeal = ad.good_price_deal
  const isOverpriced = ad.price_vs_new_ratio > 1
  const accent = AD_TYPE_ACCENT[ad.ad_type] || DEFAULT_ACCENT

  const [zoomed, setZoomed] = useState(false)

  useEffect(() => {
    if (!zoomed) return
    const onKey = e => { if (e.key === 'Escape') setZoomed(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [zoomed])

  return (
    <article
      onClick={() => onClick(ad)}
      className="group relative bg-white dark:bg-slate-900 rounded-2xl overflow-hidden cursor-pointer hover:shadow-[0_4px_10px_rgba(0,0,0,0.15)] hover:scale-[1.02] transition-all duration-200 animate-fadeIn"
    >

      {/* Image */}
      <div className="relative">
        <div
          className={`aspect-[4/3] bg-slate-100 dark:bg-slate-800 overflow-hidden relative ${img ? 'cursor-zoom-in' : ''}`}
          onClick={img ? (e => { e.stopPropagation(); setZoomed(true) }) : undefined}
        >
          {img ? (
            <>
              <img
                src={img}
                alt={ad.title}
                loading="lazy"
                className="w-full h-full object-contain group-hover:scale-105 transition-transform duration-300"
                onError={e => { e.target.style.display = 'none' }}
              />
              <div className="absolute inset-0 flex items-center justify-center bg-black/0 group-hover:bg-black/10 transition-colors pointer-events-none">
                <div className="w-8 h-8 rounded-full bg-black/40 backdrop-blur-sm flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                  <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M11 19a8 8 0 100-16 8 8 0 000 16zM11 8v6M8 11h6" />
                  </svg>
                </div>
              </div>
            </>
          ) : (
            <div className="w-full h-full flex flex-col items-center justify-center gap-1.5 text-slate-300 dark:text-slate-600">
              <svg className="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.3}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 3l18 18M9.5 5h4l1.2 2H19a2 2 0 012 2v9a2 2 0 01-2 2H8m-3 0a2 2 0 01-2-2V9a2 2 0 012-2h.5" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.5 13a3.5 3.5 0 01-5.607 2.803" />
              </svg>
              <span className="text-[11px] font-medium">Нема слика</span>
            </div>
          )}

          {/* Wishlist heart */}
          {onWishlistToggle && (
            <button
              onClick={e => { e.stopPropagation(); onWishlistToggle(ad) }}
              className={`absolute top-1.5 right-1.5 p-1.5 rounded-full backdrop-blur-sm transition-all ${
                isSaved
                  ? 'bg-red-500 text-white shadow-md'
                  : 'bg-black/30 text-white/80 hover:bg-red-500 hover:text-white'
              }`}
              aria-label={isSaved ? 'Отстрани од листа на желби' : 'Зачувај'}
            >
              <svg className="w-3.5 h-3.5" fill={isSaved ? 'currentColor' : 'none'} viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
              </svg>
            </button>
          )}

          {/* Image count badge */}
          {images.length > 1 && (
            <span className="absolute bottom-1.5 right-1.5 bg-black/50 text-white text-[10px] font-mono px-1.5 py-0.5 rounded-md backdrop-blur-sm">
              {images.length} фото
            </span>
          )}

          {/* Good deal / overpriced badge on image */}
          {isGoodDeal && (
            <div className="absolute top-1.5 left-1.5 flex items-center gap-1 bg-emerald-500 text-white text-[10px] font-bold uppercase tracking-wide px-2 py-1 rounded-lg shadow-sm">
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.568 3H5.25A2.25 2.25 0 003 5.25v4.318c0 .597.237 1.169.659 1.591l9.581 9.581c.699.699 1.78.872 2.607.33a18.095 18.095 0 005.223-5.223c.542-.827.369-1.908-.33-2.607L11.16 3.66A2.25 2.25 0 009.568 3z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 6h.008v.008H6V6z" />
              </svg>
              Добра цена
            </div>
          )}
          {!isGoodDeal && isOverpriced && (
            <div className="absolute top-1.5 left-1.5 bg-amber-500 text-white text-[10px] font-bold uppercase tracking-wide px-2 py-1 rounded-lg shadow-sm">
              Прескапо
            </div>
          )}
        </div>
      </div>

      {/* Image zoom lightbox -- portaled to <body> so it's never nested
          inside the card's `hover:scale-*` ancestor. A transformed ancestor
          creates a new containing block for `position: fixed`, which broke
          the overlay's sizing and fed back into the hover state, causing a
          flicker/freeze loop. */}
      {zoomed && img && createPortal(
        <div
          onClick={e => { e.stopPropagation(); setZoomed(false) }}
          className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-6 animate-fadeIn"
        >
          <button
            onClick={e => { e.stopPropagation(); setZoomed(false) }}
            className="absolute top-4 right-4 p-2 rounded-full bg-white/10 text-white hover:bg-white/20 transition-colors"
            aria-label="Затвори"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
          <img
            src={img}
            alt={ad.title}
            className="max-w-full max-h-full object-contain rounded-lg cursor-zoom-out"
          />
        </div>,
        document.body
      )}

      <div className="p-3.5 space-y-2.5">
        {/* Tags row */}
        {tags.length > 0 && (
          <div className="inline-flex items-center gap-1.5 bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 text-xs font-medium px-2 py-1 rounded-md">
            {tags.map((tag, i) => (
              <span key={tag} className="flex items-center gap-1.5">
                {i > 0 && <span className="text-slate-300 dark:text-slate-600">|</span>}
                {tag}
              </span>
            ))}
          </div>
        )}

        {/* Title */}
        <h3 className="text-base font-bold text-slate-900 dark:text-slate-100 line-clamp-2 leading-snug min-h-[2.75rem]">
          {formatTitle(ad.title)}
        </h3>

        {/* Price + location */}
        <div className="flex items-end justify-between gap-2">
          <div>
            {ad.price_eur ? (
              <span className={`text-base font-bold font-mono ${accent.price}`}>
                {Number(ad.price_eur).toLocaleString('mk-MK')} €
              </span>
            ) : (
              <span className="text-sm font-medium text-slate-500 dark:text-slate-400">По договор</span>
            )}
          </div>
          {ad.location && (
            <span className="text-[11px] font-medium text-slate-500 dark:text-slate-400 flex items-center gap-0.5 shrink-0 min-w-0 truncate max-w-[40%]">
              <svg className="w-3.5 h-3.5 shrink-0 text-red-600" viewBox="0 0 24 24">
                <path fill="currentColor" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                <circle cx="12" cy="10.5" r="2.75" className="fill-white dark:fill-slate-900" />
              </svg>
              <span className="truncate">{ad.location}</span>
            </span>
          )}
        </div>

        {/* Date */}
        {(ad.posted_date || ad.scraped_at) && (
          <p className="text-[11px] font-medium text-slate-500 dark:text-slate-400 font-mono">
            {formatDate(ad.posted_date || ad.scraped_at)}
          </p>
        )}
      </div>
    </article>
  )
}
