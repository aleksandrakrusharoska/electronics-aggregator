import { dealInfo, formatEur } from '../utils/formatPrice'

// How the price compares with the same model new: a soft green "−40% · нов
// 273 €" for a good deal, a soft red "+12% над нов" for an overpriced ad —
// tinted, not solid, so it reads as information rather than an alarm. Used
// on the card (over the photo) and in the list row.
const DEAL_CLS = 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200 dark:bg-emerald-950/80 dark:text-emerald-300 dark:ring-emerald-800'
const OVER_CLS = 'bg-rose-50 text-rose-700 ring-1 ring-rose-200 dark:bg-rose-950/80 dark:text-rose-300 dark:ring-rose-800'

export default function PriceBadge({ ad, className = '' }) {
  const ratio = Number(ad.price_vs_new_ratio)
  const base = `text-[11px] font-semibold px-2 py-1 rounded-lg whitespace-nowrap ${className}`

  if (ad.good_price_deal) {
    const deal = dealInfo(ad)
    return deal ? (
      <span className={`${base} ${DEAL_CLS}`} title={`${deal.percent}% под цената на нов уред (${formatEur(deal.newEur)})`}>
        −{deal.percent}% · нов {formatEur(deal.newEur)}
      </span>
    ) : (
      <span className={`${base} ${DEAL_CLS}`}>Добра цена</span>
    )
  }
  if (ratio > 1) {
    const over = Math.round((ratio - 1) * 100)
    return (
      <span className={`${base} ${OVER_CLS}`} title="Поскапо од истиот уред нов">
        {over > 0 ? `+${over}% над нов` : 'Поскапо од нов'}
      </span>
    )
  }
  return null
}
