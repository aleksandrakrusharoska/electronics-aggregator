import { useEffect, useRef, useState } from 'react'
import { fetchSimilar } from '../api/client'
import { formatDate } from '../utils/formatDate'
import { inferSource } from '../utils/inferSource'
import AdChat from './AdChat'

const SOURCE_LABELS = { reklama5: 'Reklama5', pazar3: 'Pazar3' }
const CONDITION_MK = {
  new: 'Нов', like_new: 'Како нов', used: 'Користен', for_parts: 'За делови',
}
const SELLER_TYPE_MK = { private: 'Физичко лице', business: 'Правно лице' }

const DESC_TRUNCATE_LEN = 600

function dedupeDescriptionSpecs(description, specs) {
  if (!description) return description
  const specValues = Object.values(specs || {})
    .map(v => String(v).toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim())
    .filter(v => v.length >= 3)
  if (specValues.length === 0) return description

  const kept = []
  for (const rawLine of description.split('\n')) {
    const line = rawLine.trim()
    const header = line.replace(/^[^\p{L}]*/u, '').replace(/:?\s*$/, '').toLowerCase()
    if (['спецификации', 'спецификација', 'specs', 'specifications'].includes(header)) continue

    const match = line.match(/^([\p{L}\p{N} /\-]{2,40}):\s*(.+)$/u)
    if (match) {
      const normValue = match[2].toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim()
      if (normValue.length >= 3 && specValues.some(sv => sv.includes(normValue) || normValue.includes(sv))) {
        continue
      }
    }
    kept.push(rawLine)
  }
  return kept.join('\n').replace(/\n{3,}/g, '\n\n').trim()
}

function truncateAtWord(text, len) {
  if (text.length <= len) return text
  const cut = text.lastIndexOf(' ', len)
  return text.slice(0, cut > len * 0.6 ? cut : len).trimEnd() + '…'
}

export default function AdModal({ ad, onClose, isSaved, onWishlistToggle }) {
  const [currentAd, setCurrentAd] = useState(ad)
  const [imgIdx, setImgIdx] = useState(0)
  const [similar, setSimilar] = useState([])
  const [similarPageIndex, setSimilarPageIndex] = useState(0)
  const [similarPageCount, setSimilarPageCount] = useState(1)
  const [chatOpen, setChatOpen] = useState(false)
  const [descExpanded, setDescExpanded] = useState(false)
  const similarScrollRef = useRef(null)
  const images = Array.isArray(currentAd.images) ? currentAd.images : (currentAd.image_url ? [currentAd.image_url] : [])

  useEffect(() => { setCurrentAd(ad); setImgIdx(0); setDescExpanded(false) }, [ad.ad_url])

  const prev = () => setImgIdx(i => (i - 1 + images.length) % images.length)
  const next = () => setImgIdx(i => (i + 1) % images.length)

  useEffect(() => {
    const onKey = e => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowLeft'  && images.length > 1) prev()
      if (e.key === 'ArrowRight' && images.length > 1) next()
    }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [onClose, images.length])

  useEffect(() => {
    setSimilarPageIndex(0)
    similarScrollRef.current?.scrollTo({ left: 0 })
    if (!currentAd.cluster_id) { setSimilar([]); return }
    fetchSimilar(currentAd.cluster_id, currentAd.ad_url).then(setSimilar).catch(() => setSimilar([]))
  }, [currentAd.ad_url, currentAd.cluster_id])

  useEffect(() => {
    const el = similarScrollRef.current
    if (!el || similar.length === 0 || el.clientWidth === 0) { setSimilarPageCount(1); return }
    setSimilarPageCount(Math.max(1, Math.ceil(el.scrollWidth / el.clientWidth)))
  }, [similar])

  const daysSinceScraped = (() => {
    const ref = currentAd.scraped_at || currentAd.posted_date
    if (!ref) return null
    return Math.floor((Date.now() - new Date(ref).getTime()) / 86_400_000)
  })()

  const source = inferSource(currentAd)
  const specs = currentAd.specs && typeof currentAd.specs === 'object' ? currentAd.specs : {}
  const hasSpecs = Object.keys(specs).length > 0

  const sellerNotes = (() => {
    const notes = currentAd.seller_notes?.trim()
    const desc = currentAd.description?.trim()
    if (!notes) return null
    if (desc && desc.toLowerCase().includes(notes.toLowerCase())) return null
    return notes
  })()

  const isGoodDeal = currentAd.good_price_deal
  const isOverpriced = !isGoodDeal && currentAd.price_vs_new_ratio > 1
  const referenceLabel = currentAd.reference_source === 'setec'
    ? 'споредено со тековна цена на Setec.mk'
    : currentAd.reference_source === 'marketplace'
      ? 'споредено со оглас за нов истиот модел'
      : null
  const pctOfNew = currentAd.price_vs_new_ratio != null
    ? Math.round(currentAd.price_vs_new_ratio * 100)
    : null

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

      {/* Panel */}
      <div className="relative z-10 w-full sm:max-w-4xl max-h-[95dvh] bg-white dark:bg-slate-900 sm:rounded-2xl overflow-hidden flex flex-col shadow-2xl animate-slideUp">

        {/* Header */}
        <div className="flex items-start gap-3 p-5 pb-4 border-b border-slate-100 dark:border-slate-800 shrink-0">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              {source && (
                <span className="text-[11px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-violet-100 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300">
                  {SOURCE_LABELS[source] || source}
                </span>
              )}
              {currentAd.condition && (
                <span className="text-[11px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400">
                  {CONDITION_MK[currentAd.condition] || currentAd.condition}
                </span>
              )}
              {currentAd.delivery_available && (
                <span className="text-[11px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-violet-100 dark:bg-violet-900/30 text-violet-600 dark:text-violet-300">
                  Достава
                </span>
              )}
            </div>
            <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100 leading-snug">
              {currentAd.title}
            </h2>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={() => setChatOpen(v => !v)}
              className={`flex items-center gap-1.5 rounded-full pl-2.5 pr-3 py-1.5 text-xs font-semibold transition-colors ${
                chatOpen
                  ? 'bg-violet-600 text-white'
                  : 'bg-violet-100 text-violet-700 hover:bg-violet-200 dark:bg-violet-900/30 dark:text-violet-300 dark:hover:bg-violet-900/50'
              }`}
              aria-label="Прашај AI за огласов"
              title="Прашај AI за огласов"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M21 12c0 4.418-4.03 8-9 8-1.06 0-2.077-.163-3.02-.463L3 21l1.593-3.98A7.86 7.86 0 013 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
              Прашај AI
            </button>
            {onWishlistToggle && (
              <button
                onClick={() => onWishlistToggle(currentAd)}
                className={`rounded-lg p-2 transition-colors ${
                  isSaved(currentAd.ad_url)
                    ? 'text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20'
                    : 'text-slate-400 hover:text-red-400 hover:bg-slate-100 dark:hover:bg-slate-800'
                }`}
                aria-label={isSaved(currentAd.ad_url) ? 'Отстрани од листа на желби' : 'Зачувај'}
              >
                <svg className="w-5 h-5" fill={isSaved(currentAd.ad_url) ? 'currentColor' : 'none'} viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
                </svg>
              </button>
            )}
            <button
              onClick={onClose}
              className="rounded-lg p-2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
              aria-label="Затвори"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Price-vs-new banners */}
        {isGoodDeal && (
          <div className="shrink-0 px-5 py-2.5 bg-emerald-50 dark:bg-emerald-950/30 border-b border-emerald-100 dark:border-emerald-900/30">
            <div className="flex items-center gap-3">
              <svg className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M12.395 2.553a1 1 0 00-1.45-.385c-.345.23-.614.558-.822.88-.214.33-.403.713-.57 1.116-.334.804-.614 1.768-.84 2.734a31.365 31.365 0 00-.613 3.58 2.64 2.64 0 01-.945-1.067c-.328-.68-.398-1.534-.398-2.654A1 1 0 005.05 6.05 6.981 6.981 0 003 11a7 7 0 1011.95-4.95c-.592-.591-.98-.985-1.348-1.467-.363-.476-.724-1.063-1.207-2.03zM12.12 15.12A3 3 0 017 13s.879.5 2.5.5c0-1 .5-4 1.25-4.5.5 1 .786 1.293 1.371 1.879A2.99 2.99 0 0113 13a2.99 2.99 0 01-.879 2.121z" clipRule="evenodd" />
              </svg>
              <span className="text-sm font-medium text-emerald-700 dark:text-emerald-300">Добра цена</span>
              {pctOfNew != null && (
                <span className="text-xs text-emerald-600/70 dark:text-emerald-400/70">
                  {pctOfNew}% од цена на нов уред
                </span>
              )}
            </div>
            {referenceLabel && (
              <p className="mt-1 text-xs text-emerald-700/80 dark:text-emerald-300/70 pl-7 italic">
                {referenceLabel} ({Number(currentAd.reference_new_price_mkd).toLocaleString('mk-MK')} ден.)
              </p>
            )}
          </div>
        )}
        {isOverpriced && (
          <div className="shrink-0 px-5 py-2.5 bg-amber-50 dark:bg-amber-950/30 border-b border-amber-100 dark:border-amber-900/30">
            <div className="flex items-center gap-3">
              <svg className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <span className="text-sm font-medium text-amber-700 dark:text-amber-300">Прескапо</span>
              {pctOfNew != null && (
                <span className="text-xs text-amber-600/70 dark:text-amber-400/70">
                  {pctOfNew}% од цена на нов уред
                </span>
              )}
            </div>
            {referenceLabel && (
              <p className="mt-1 text-xs text-amber-700/80 dark:text-amber-300/70 pl-7 italic">
                {referenceLabel} ({Number(currentAd.reference_new_price_mkd).toLocaleString('mk-MK')} ден.)
              </p>
            )}
          </div>
        )}

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto">
          <div className="grid sm:grid-cols-2 gap-0">

            {/* Left: image + price */}
            <div className="p-5 space-y-4">
              {/* Gallery */}
              {images.length > 0 ? (
                <div className="space-y-2">
                  <div className="aspect-[4/3] bg-slate-100 dark:bg-slate-800 rounded-xl overflow-hidden relative group/img">
                    <img
                      src={images[imgIdx]}
                      alt={currentAd.title}
                      className="w-full h-full object-contain"
                      onError={e => { e.target.style.display = 'none' }}
                    />
                    {images.length > 1 && (
                      <>
                        <button
                          onClick={prev}
                          className="absolute left-2 top-1/2 -translate-y-1/2 w-8 h-8 rounded-full bg-black/40 hover:bg-black/60 text-white flex items-center justify-center opacity-0 group-hover/img:opacity-100 transition-opacity backdrop-blur-sm"
                          aria-label="Претходна слика"
                        >
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
                          </svg>
                        </button>
                        <button
                          onClick={next}
                          className="absolute right-2 top-1/2 -translate-y-1/2 w-8 h-8 rounded-full bg-black/40 hover:bg-black/60 text-white flex items-center justify-center opacity-0 group-hover/img:opacity-100 transition-opacity backdrop-blur-sm"
                          aria-label="Следна слика"
                        >
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                          </svg>
                        </button>
                        <div className="absolute bottom-2 left-1/2 -translate-x-1/2 flex gap-1">
                          {images.map((_, i) => (
                            <button
                              key={i}
                              onClick={() => setImgIdx(i)}
                              className={`w-1.5 h-1.5 rounded-full transition-all ${i === imgIdx ? 'bg-white w-3' : 'bg-white/50'}`}
                            />
                          ))}
                        </div>
                      </>
                    )}
                  </div>
                  {images.length > 1 && (
                    <div className="flex gap-1.5 overflow-x-auto pb-1">
                      {images.map((src, i) => (
                        <button
                          key={i}
                          onClick={() => setImgIdx(i)}
                          className={`shrink-0 w-14 h-14 rounded-lg overflow-hidden border-2 transition-colors ${
                            i === imgIdx ? 'border-violet-500' : 'border-transparent hover:border-slate-300 dark:hover:border-slate-600'
                          }`}
                        >
                          <img src={src} alt="" className="w-full h-full object-contain" onError={e => { e.target.style.display = 'none' }} />
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                <div className="aspect-[4/3] bg-slate-100 dark:bg-slate-800 rounded-xl flex items-center justify-center">
                  <svg className="w-16 h-16 text-slate-300 dark:text-slate-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                  </svg>
                </div>
              )}

              {/* Price */}
              <div className="flex items-baseline gap-2 flex-wrap">
                {currentAd.price_eur ? (
                  <span className="text-2xl font-bold text-violet-600 dark:text-violet-400 font-mono">
                    {Number(currentAd.price_eur).toLocaleString('mk-MK')} €
                  </span>
                ) : (
                  <span className="text-lg text-slate-400 dark:text-slate-500">По договор</span>
                )}
                {currentAd.price_mkd && (
                  <span className="text-sm text-slate-400 dark:text-slate-500 font-mono">
                    ≈ {Number(currentAd.price_mkd).toLocaleString('mk-MK')} МКД
                  </span>
                )}
              </div>

              {/* Meta */}
              <dl className="space-y-1.5 text-sm">
                {currentAd.location && (
                  <div className="flex items-center gap-2 text-slate-600 dark:text-slate-400">
                    <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                    </svg>
                    {currentAd.location}
                  </div>
                )}
                {currentAd.seller_name && (
                  <div className="flex items-center gap-2 text-slate-600 dark:text-slate-400">
                    <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                    </svg>
                    <span>{currentAd.seller_name}</span>
                    {currentAd.seller_type && (
                      <span className="text-[11px] text-slate-400 dark:text-slate-500">
                        ({SELLER_TYPE_MK[currentAd.seller_type] || currentAd.seller_type})
                      </span>
                    )}
                  </div>
                )}
                {currentAd.delivery_available && (
                  <div className="flex items-center gap-2 text-emerald-600 dark:text-emerald-400">
                    <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
                    </svg>
                    Достава можна
                  </div>
                )}
                {(currentAd.posted_date || currentAd.scraped_at) && (
                  <div className="text-slate-400 dark:text-slate-500 text-xs">
                    Огласено: {formatDate(currentAd.posted_date || currentAd.scraped_at)}
                  </div>
                )}
              </dl>

              {/* Cluster tag */}
              {currentAd.cluster_label && (
                <div className="flex items-center gap-2 text-xs text-slate-400 dark:text-slate-500 bg-slate-50 dark:bg-slate-800/60 rounded-lg px-3 py-2 border border-slate-100 dark:border-slate-800">
                  <svg className="w-3.5 h-3.5 shrink-0 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M7 20l4-16m2 16l4-16M6 9h14M4 15h14" />
                  </svg>
                  <span className="font-mono truncate">{currentAd.cluster_label}</span>
                </div>
              )}

              {/* Stale warning */}
              {daysSinceScraped !== null && daysSinceScraped > 30 && (
                <div className="flex items-start gap-2 text-xs text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 rounded-lg px-3 py-2 border border-amber-100 dark:border-amber-800">
                  <svg className="w-3.5 h-3.5 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span>Овој оглас е објавен пред повеќе од {daysSinceScraped} дена. Можно е производот да е веќе продаден.</span>
                </div>
              )}

              {/* Link */}
              {currentAd.ad_url && (
                <a
                  href={currentAd.ad_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-700 text-white text-sm font-medium transition-colors"
                >
                  Погледни оглас
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                  </svg>
                </a>
              )}
            </div>

            {/* Right: specs + description */}
            <div className="p-5 space-y-4 border-t sm:border-t-0 sm:border-l border-slate-100 dark:border-slate-800">

              {/* Specs */}
              {hasSpecs && (
                <div>
                  <h4 className="text-xs font-semibold uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-2">
                    Спецификации
                  </h4>
                  <dl className="space-y-0">
                    {Object.entries(specs).map(([k, v]) => (
                      <div key={k} className="flex gap-2 text-sm py-1.5 border-b border-slate-50 dark:border-slate-800 last:border-0">
                        <dt className="text-slate-500 dark:text-slate-500 shrink-0 w-2/5">{k}</dt>
                        <dd className="text-slate-800 dark:text-slate-200 font-medium min-w-0 break-words">{v}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              )}

              {/* Description */}
              {currentAd.description && (() => {
                const cleanedDescription = dedupeDescriptionSpecs(currentAd.description, specs)
                const isLongDesc = cleanedDescription.length > DESC_TRUNCATE_LEN
                const displayedDescription = descExpanded || !isLongDesc
                  ? cleanedDescription
                  : truncateAtWord(cleanedDescription, DESC_TRUNCATE_LEN)
                return (
                  <div>
                    <h4 className="text-xs font-semibold uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-2">
                      Опис
                    </h4>
                    <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed whitespace-pre-line">
                      {displayedDescription}
                    </p>
                    {isLongDesc && (
                      <button
                        onClick={() => setDescExpanded(v => !v)}
                        className="mt-1 text-xs font-semibold text-violet-600 dark:text-violet-400 hover:underline"
                      >
                        {descExpanded ? 'Прочитај помалку' : 'Прочитај повеќе'}
                      </button>
                    )}
                  </div>
                )
              })()}

              {/* Seller notes */}
              {sellerNotes && (
                <div>
                  <h4 className="text-xs font-semibold uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-2">
                    Клучни инфо
                  </h4>
                  <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed italic">
                    {sellerNotes}
                  </p>
                </div>
              )}

              {!hasSpecs && !currentAd.description && !sellerNotes && (
                <p className="text-sm text-slate-400 dark:text-slate-600 italic">
                  Нема дополнителни информации
                </p>
              )}
            </div>
          </div>

          {/* Similar products */}
          {similar.length > 0 && (
            <div className="border-t border-slate-100 dark:border-slate-800 px-5 py-4">
              <div className="flex items-center justify-between mb-3">
                <h4 className="text-xs font-semibold uppercase tracking-widest text-slate-400 dark:text-slate-500">
                  Слични производи
                </h4>
                <div className="flex gap-1">
                  <button
                    onClick={() => similarScrollRef.current?.scrollBy({ left: -similarScrollRef.current.clientWidth, behavior: 'smooth' })}
                    className="w-7 h-7 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 flex items-center justify-center text-slate-500 dark:text-slate-400 transition-colors"
                    aria-label="Scroll left"
                  >
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
                    </svg>
                  </button>
                  <button
                    onClick={() => similarScrollRef.current?.scrollBy({ left: similarScrollRef.current.clientWidth, behavior: 'smooth' })}
                    className="w-7 h-7 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 flex items-center justify-center text-slate-500 dark:text-slate-400 transition-colors"
                    aria-label="Scroll right"
                  >
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                    </svg>
                  </button>
                </div>
              </div>
              <div
                ref={similarScrollRef}
                onScroll={e => {
                  const { scrollLeft, scrollWidth, clientWidth } = e.currentTarget
                  const pages = Math.max(1, Math.ceil(scrollWidth / clientWidth))
                  // Map scrollLeft proportionally onto [0, pages-1] using the
                  // actual scrollable range, not clientWidth directly — when
                  // content is only slightly wider than the viewport (e.g. 6
                  // items just barely needing a 2nd page), the real max
                  // scroll distance is much smaller than a full clientWidth,
                  // so dividing by clientWidth would never reach the last page.
                  const maxScroll = scrollWidth - clientWidth
                  const idx = maxScroll > 0 ? Math.round((scrollLeft / maxScroll) * (pages - 1)) : 0
                  setSimilarPageCount(pages)
                  setSimilarPageIndex(Math.min(pages - 1, Math.max(0, idx)))
                }}
                className="flex gap-3 overflow-x-auto pb-1 scrollbar-hide"
              >
                {similar.map(s => {
                  const thumb = Array.isArray(s.images) ? s.images[0] : null
                  return (
                    <button
                      key={s.ad_url}
                      onClick={() => { setCurrentAd(s); setImgIdx(0) }}
                      className="shrink-0 w-36 text-left rounded-xl border border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/60 hover:border-violet-300 dark:hover:border-violet-700 hover:shadow-sm transition-all overflow-hidden"
                    >
                      <div className="w-full h-24 bg-slate-100 dark:bg-slate-800 overflow-hidden">
                        {thumb
                          ? <img src={thumb} alt={s.title} className="w-full h-full object-contain" onError={e => { e.target.style.display = 'none' }} />
                          : <div className="w-full h-full flex items-center justify-center">
                              <svg className="w-8 h-8 text-slate-300 dark:text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                              </svg>
                            </div>
                        }
                      </div>
                      <div className="p-2">
                        <p className="text-xs text-slate-700 dark:text-slate-300 line-clamp-2 leading-tight mb-1">{s.title}</p>
                        {s.price_eur && (
                          <p className="text-xs font-semibold text-violet-600 dark:text-violet-400 font-mono">
                            {Number(s.price_eur).toLocaleString('mk-MK')} €
                          </p>
                        )}
                      </div>
                    </button>
                  )
                })}
              </div>
              {similarPageCount > 1 && (
                <div className="flex justify-center gap-1.5 mt-2">
                  {Array.from({ length: similarPageCount }).map((_, i) => (
                    <span
                      key={i}
                      className={`w-1.5 h-1.5 rounded-full transition-colors ${
                        i === similarPageIndex ? 'bg-violet-500' : 'bg-slate-200 dark:bg-slate-700'
                      }`}
                    />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* AI chat panel — opened via the header icon, width matches the
            specs/description column */}
        {chatOpen && (
          <div className="absolute bottom-4 left-4 right-4 sm:left-1/2 z-20 flex justify-end">
            <div className="w-full h-[420px] max-h-[70vh] bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-800 flex flex-col overflow-hidden animate-slideUp">
              <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100 dark:border-slate-800 shrink-0">
                <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">AI асистент</span>
                <button
                  onClick={() => setChatOpen(false)}
                  className="rounded-lg p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                  aria-label="Затвори чат"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
              <div className="flex-1 min-h-0">
                <AdChat ad={currentAd} />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
