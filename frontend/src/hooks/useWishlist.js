import { useState, useEffect, useCallback } from 'react'

const KEY = 'wishlist_ads'

function load() {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || '[]')
    // Older versions stored full ad snapshots (title/price/images at
    // save-time, never refreshed — could go stale forever). Migrate those
    // to plain ad_url strings; live data is now fetched on demand instead.
    return raw.map(item => (typeof item === 'string' ? item : item.ad_url)).filter(Boolean)
  } catch {
    return []
  }
}

function save(urls) {
  localStorage.setItem(KEY, JSON.stringify(urls))
}

export function useWishlist() {
  const [wishlist, setWishlist] = useState(load)

  useEffect(() => { save(wishlist) }, [wishlist])

  const toggle = useCallback(adOrUrl => {
    const url = typeof adOrUrl === 'string' ? adOrUrl : adOrUrl.ad_url
    setWishlist(prev =>
      prev.includes(url) ? prev.filter(u => u !== url) : [url, ...prev]
    )
  }, [])

  const isSaved = useCallback(
    ad_url => wishlist.includes(ad_url),
    [wishlist]
  )

  const clear = useCallback(() => setWishlist([]), [])

  return { wishlist, toggle, isSaved, clear }
}
