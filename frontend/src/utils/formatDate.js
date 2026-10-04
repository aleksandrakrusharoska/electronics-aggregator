const MONTHS_MK = [
  'Јануари', 'Февруари', 'Март', 'Април', 'Мај', 'Јуни',
  'Јули', 'Август', 'Септември', 'Октомври', 'Ноември', 'Декември',
]

// short: true gives "12.09." (this year) / "12.09.2025" instead of
// "12 Септември 2026" — for the card, where the date shares a row with the
// location and a long month name used to squeeze the town out entirely.
export function formatDate(dateStr, { short = false } = {}) {
  if (!dateStr) return null
  const date = new Date(dateStr)
  if (isNaN(date)) return null

  const now = new Date()
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const dateStart = new Date(date.getFullYear(), date.getMonth(), date.getDate())
  const diffDays = Math.round((todayStart - dateStart) / 86_400_000)

  if (diffDays === 0) return 'Денес'
  if (diffDays === 1) return 'Вчера'
  if (diffDays === 2) return 'Пред 2 дена'

  if (short) {
    const dm = `${String(date.getDate()).padStart(2, '0')}.${String(date.getMonth() + 1).padStart(2, '0')}.`
    return date.getFullYear() === now.getFullYear() ? dm : `${dm}${date.getFullYear()}`
  }
  return `${date.getDate()} ${MONTHS_MK[date.getMonth()]} ${date.getFullYear()}`
}
