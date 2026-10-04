// Euro prices are converted from denars (÷ 61.5), so their decimals are a
// conversion artefact ("390.24 €", "162.6 €"). Show whole euros with the
// Macedonian thousands separator ("1.250 €"), written out here because
// browsers without Macedonian locale data fall back to "1,250".
export function formatEur(value) {
  const n = Math.round(Number(value))
  return `${String(n).replace(/\B(?=(\d{3})+(?!\d))/g, '.')} €`
}

// How far below the reference price (the price of the same brand + model
// when new) an ad is, for the good-deal badge: { percent: 62, newEur: 389 }.
// null when the ad has no usable comparison.
export function dealInfo(ad) {
  const ratio = Number(ad.price_vs_new_ratio)
  const refMkd = Number(ad.reference_new_price_mkd)
  if (!(ratio > 0 && ratio < 1) || !(refMkd > 0)) return null
  return { percent: Math.round((1 - ratio) * 100), newEur: refMkd / 61.5 }
}
