export function inferSource(ad) {
  if (ad.source) return ad.source
  if (typeof ad.ad_url === 'string') {
    if (ad.ad_url.includes('pazar3.mk')) return 'pazar3'
    if (ad.ad_url.includes('reklama5.mk')) return 'reklama5'
  }
  return null
}
