import { formatDate } from '../utils/formatDate'
import { inferSource } from '../utils/inferSource'

const SOURCE_COLORS = {
  reklama5: 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300',
  pazar3:   'bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300',
}

const AD_TYPE_ACCENT = {
  service: { bg: 'bg-amber-200', shadow: 'hover:shadow-amber-200/25' },
  wanted:  { bg: 'bg-emerald-200', shadow: 'hover:shadow-emerald-200/25' },
}
const DEFAULT_ACCENT = { bg: 'bg-violet-400', shadow: 'hover:shadow-violet-400/25' }

const CONDITION_LABELS = {
  'New':             { label: 'Нов',              cls: 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300' },
  'Used - Like New': { label: 'Како нов',          cls: 'bg-teal-100 dark:bg-teal-900/30 text-teal-700 dark:text-teal-300' },
  'Used - Good':     { label: 'Добра состојба',    cls: 'bg-sky-100 dark:bg-sky-900/30 text-sky-700 dark:text-sky-300' },
  'Used - Fair':     { label: 'Солидна состојба',  cls: 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300' },
  'Used':            { label: 'Користен',          cls: 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400' },
  'For parts':       { label: 'За делови',         cls: 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300' },
}

function Badge({ children, className }) {
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide ${className}`}>
      {children}
    </span>
  )
}

export default function AdCard({ ad, onClick, isSaved, onWishlistToggle }) {
  const images = Array.isArray(ad.images) ? ad.images : (ad.image_url ? [ad.image_url] : [])
  const img = images[0]
  const cond = CONDITION_LABELS[ad.condition]
  const source = inferSource(ad)
  const srcCls = SOURCE_COLORS[source] || 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400'

  const isGoodDeal = ad.good_price_deal
  const isOverpriced = ad.price_vs_new_ratio > 1
  const accent = AD_TYPE_ACCENT[ad.ad_type] || DEFAULT_ACCENT

  return (
    <article
      onClick={() => onClick(ad)}
      className={`group relative bg-white dark:bg-slate-900 rounded-2xl overflow-hidden cursor-pointer shadow-md hover:shadow-xl transition-shadow duration-200 animate-fadeIn ${accent.shadow}`}
    >
      {/* Image */}
      <div className="relative">
        <div className="aspect-[4/3] bg-slate-100 dark:bg-slate-800 overflow-hidden relative">
          {img ? (
            <img
              src={img}
              alt={ad.title}
              loading="lazy"
              className="w-full h-full object-contain group-hover:scale-105 transition-transform duration-300"
              onError={e => { e.target.style.display = 'none' }}
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center">
              <svg className="w-12 h-12 text-slate-300 dark:text-slate-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
            </div>
          )}

          {/* Diagonal color accent */}
          <div
            className={`absolute -bottom-3 -left-3 w-20 h-20 ${accent.bg} pointer-events-none`}
            style={{ clipPath: 'polygon(0 100%, 100% 100%, 0 0)' }}
          />

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

      <div className="p-3 space-y-2">
        {/* Badges row */}
        <div className="flex items-center gap-1 flex-wrap">
          {source && <Badge className={srcCls}>{source}</Badge>}
          {cond && <Badge className={cond.cls}>{cond.label}</Badge>}
          {ad.delivery_available && (
            <Badge className="bg-violet-100 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300">Достава</Badge>
          )}
        </div>

        {/* Title */}
        <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100 line-clamp-2 leading-snug">
          {ad.title}
        </h3>

        {/* Price + location */}
        <div className="flex items-end justify-between gap-2">
          <div>
            {ad.price_eur ? (
              <span className="text-base font-bold text-violet-600 dark:text-violet-400 font-mono">
                {Number(ad.price_eur).toLocaleString('mk-MK')} €
              </span>
            ) : (
              <span className="text-sm text-slate-400 dark:text-slate-500">По договор</span>
            )}
          </div>
          {ad.location && (
            <span className="text-[11px] text-slate-400 dark:text-slate-500 flex items-center gap-0.5 shrink-0 min-w-0 truncate max-w-[40%]">
              <svg className="w-3 h-3 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              <span className="truncate">{ad.location}</span>
            </span>
          )}
        </div>

        {/* Date */}
        {(ad.posted_date || ad.scraped_at) && (
          <p className="text-[11px] text-slate-400 dark:text-slate-600 font-mono">
            {formatDate(ad.posted_date || ad.scraped_at)}
          </p>
        )}
      </div>
    </article>
  )
}
