const API_ROOT = import.meta.env.VITE_API_URL ?? ''
const BASE = `${API_ROOT}/api/ads`

export async function fetchAds(filters = {}) {
  const { source, category, condition, min_price, max_price, q, sort, page, good_deal_only, ad_type } = filters
  const params = new URLSearchParams()
  if (source)         params.set('source', source)
  if (category)       params.set('category', category)
  if (condition)      params.set('condition', condition)
  if (min_price)      params.set('min_price', min_price)
  if (max_price)      params.set('max_price', max_price)
  if (q)              params.set('q', q)
  if (sort)           params.set('sort', sort)
  if (page)           params.set('page', page)
  if (good_deal_only) params.set('good_deal_only', 'true')
  if (ad_type)        params.set('ad_type', ad_type)

  const res = await fetch(`${BASE}?${params}`)
  if (!res.ok) throw new Error('fetch_failed')
  return res.json()
}

export async function fetchStats() {
  const res = await fetch(`${BASE}/stats`)
  if (!res.ok) throw new Error('Грешка при вчитување статистики')
  return res.json()
}

export async function fetchCategories() {
  const res = await fetch(`${BASE}/categories`)
  if (!res.ok) throw new Error('Грешка при вчитување категории')
  return res.json()
}

export async function fetchBrandStats() {
  const res = await fetch(`${BASE}/analytics/brands`)
  if (!res.ok) throw new Error('fetch_failed')
  return res.json()
}

export async function fetchDepreciation() {
  const res = await fetch(`${BASE}/analytics/depreciation`)
  if (!res.ok) throw new Error('fetch_failed')
  return res.json()
}

export async function fetchSimilar(clusterId, excludeUrl) {
  const params = new URLSearchParams({ cluster_id: clusterId, limit: 6 })
  if (excludeUrl) params.set('exclude_url', excludeUrl)
  const res = await fetch(`${BASE}/similar?${params}`)
  if (!res.ok) return []
  return res.json()
}

export async function chatAboutAd(ad, messages) {
  const res = await fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ad, messages }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'chat_failed')
  }
  return res.json()
}
