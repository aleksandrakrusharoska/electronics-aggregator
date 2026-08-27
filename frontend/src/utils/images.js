// Some source sites (e.g. pazar3) return their own "no photo" placeholder
// image URL instead of omitting the image entirely -- scraped as if it were
// a real photo. Treat those as "no image" too.
const PLACEHOLDER_RE = /nothumbnail|no-?image|no_photo/i

export function firstRealImage(images) {
  const first = Array.isArray(images) ? images[0] : images
  return first && !PLACEHOLDER_RE.test(first) ? first : null
}
