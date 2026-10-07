// Titles are shown as the seller published them (Latin or Cyrillic, no
// transliteration); only the first letter is capitalized.
export function formatTitle(title) {
  if (!title) return title
  const i = title.search(/\S/)
  if (i === -1) return title
  const firstWord = title.slice(i).match(/^\S+/)?.[0] ?? ''
  // Leave a word with its own internal capitals alone: "iPhone" must not
  // become "IPhone". A plain "iphone" or "samsung" is still capitalized.
  if (/\p{Lu}/u.test(firstWord.slice(1))) return title
  return title.slice(0, i) + title[i].toUpperCase() + title.slice(i + 1)
}
