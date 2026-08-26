// Ad titles come from pazar3/reklama5 sellers typing in either script --
// proper Macedonian Cyrillic, "vernacular" Latin (no diacritics, e.g.
// "prodavam", "novo"), or diacritic Latin (č/š/ž). We normalize display to
// Cyrillic while leaving brand/model names (iPhone, PS5, RTX 4090...) in
// Latin, since transliterating those would be wrong, not just inconsistent.

// Diacritic Latin -> Cyrillic (unambiguous, safe for any word using these).
// Longest sequences first so e.g. "dž" isn't split into "d" + "ž".
const DIACRITIC_MAP = [
  ['dž', 'џ'], ['Dž', 'Џ'], ['DŽ', 'Џ'],
  ['lj', 'љ'], ['Lj', 'Љ'], ['LJ', 'Љ'],
  ['nj', 'њ'], ['Nj', 'Њ'], ['NJ', 'Њ'],
  ['č', 'ч'], ['Č', 'Ч'],
  ['š', 'ш'], ['Š', 'Ш'],
  ['ž', 'ж'], ['Ž', 'Ж'],
  ['ć', 'ќ'], ['Ć', 'Ќ'],
  ['đ', 'ѓ'], ['Đ', 'Ѓ'],
]

// Common vernacular (no-diacritic) Macedonian words seen in classifieds --
// covers the bulk of everyday listing phrasing that a character-level
// transliteration can't handle reliably (plain "c"/"s"/"z" are ambiguous
// without this).
const WORD_MAP = {
  prodavam: 'продавам', prodava: 'продава', prodavame: 'продаваме',
  kupuvam: 'купувам', kupuva: 'купува', baram: 'барам',
  se: 'се', prodazba: 'продажба', kupuvanje: 'купување', zamena: 'замена',
  nov: 'нов', nova: 'нова', novo: 'ново', novi: 'нови',
  koristen: 'користен', koristena: 'користена', koristeno: 'користено',
  nekoristen: 'некористен', nekoristena: 'некористена', nekoristeno: 'некористено',
  ispraven: 'исправен', ispravna: 'исправна', ispravno: 'исправно',
  odlicna: 'одлична', odlicno: 'одлично', odlicen: 'одличен',
  sostojba: 'состојба', garancija: 'гаранција', racun: 'сметка',
  cena: 'цена', dogovor: 'договор', povolno: 'поволно', itno: 'итно',
  hitno: 'итно', bez: 'без', so: 'со', za: 'за', od: 'од', do: 'до',
  na: 'на', vo: 'во', i: 'и', ne: 'не', ima: 'има', nema: 'нема',
  popravka: 'поправка', servis: 'сервис', servisiranje: 'сервисирање',
  dostava: 'достава', transport: 'превоз', montaza: 'монтажа',
  telefon: 'телефон', kompjuter: 'компјутер', laptop: 'лаптоп',
  slusalki: 'слушалки', polovna: 'половна', polovno: 'половно',
  prodadeno: 'продадено', rezervirano: 'резервирано',
  ili: 'или', kako: 'како', komplet: 'комплет', delovi: 'делови',
  original: 'оригинал', originalen: 'оригинален', originalna: 'оригинална',
  polovni: 'половни', polovna: 'половна', polovno: 'половно',
  skopje: 'Скопје', bitola: 'Битола', ohrid: 'Охрид', tetovo: 'Тетово',
  prilep: 'Прилеп', struga: 'Струга', kumanovo: 'Куманово', veles: 'Велес',
  strumica: 'Струмица', gostivar: 'Гостивар',
}

// Brand / product / tech terms to always leave in Latin, matched
// case-insensitively as whole words.
const BRAND_WORDS = new Set([
  'iphone', 'ipad', 'macbook', 'imac', 'apple', 'airpods', 'watch',
  'samsung', 'galaxy', 'xiaomi', 'redmi', 'poco', 'huawei', 'honor',
  'oppo', 'oneplus', 'nokia', 'sony', 'playstation', 'xbox', 'nintendo',
  'lenovo', 'thinkpad', 'hp', 'dell', 'asus', 'acer', 'msi', 'lg',
  'philips', 'jbl', 'bose', 'beats', 'canon', 'nikon', 'gopro', 'dji',
  'amd', 'intel', 'nvidia', 'rtx', 'gtx', 'ryzen', 'core', 'ssd', 'hdd',
  'ram', 'led', 'oled', 'qled', 'usb', 'hdmi', 'wifi', 'bluetooth',
  'ps3', 'ps4', 'ps5', 'ps2', 'switch',
])

function isBrandOrCode(word) {
  const bare = word.replace(/[^a-zA-Z0-9]/g, '')
  if (!bare) return false
  if (/\d/.test(bare)) return true // model numbers/codes: "4090", "13", "A54"
  if (bare.length > 1 && bare === bare.toUpperCase() && /[A-Z]/.test(bare)) return true // acronyms: "SSD", "LED"
  return BRAND_WORDS.has(bare.toLowerCase())
}

function transliterateWord(word) {
  const lower = word.toLowerCase()
  // Normalize stray accents (á, é, í...) some scraped titles pick up --
  // strip combining diacritics down to plain ASCII for the dictionary
  // lookup key only; the diacritic-preserving branch below still checks
  // the original word for real Macedonian digraphs (č š ž ć đ).
  const stripped = lower.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z]/g, '')
  if (WORD_MAP[stripped]) {
    const cyr = WORD_MAP[stripped]
    // Preserve simple capitalization (first letter uppercase if the source was).
    if (word[0] === word[0].toUpperCase() && /[a-zA-Z]/.test(word[0])) {
      return cyr[0].toUpperCase() + cyr.slice(1)
    }
    return cyr
  }
  // Character-level fallback: only safe when the word actually contains a
  // Macedonian Latin diacritic (č š ž ć đ) -- plain ASCII is too ambiguous
  // to guess at without a full dictionary, so we leave it as-is.
  if (/[čšžćđ]/i.test(word)) {
    let out = word
    for (const [from, to] of DIACRITIC_MAP) out = out.split(from).join(to)
    return out
  }
  return word
}

export function macedonianize(text) {
  if (!text) return text
  return text
    .split(/(\s+)/) // keep whitespace tokens so spacing is preserved
    .map(tok => (/\s+/.test(tok) || isBrandOrCode(tok) ? tok : transliterateWord(tok)))
    .join('')
}

export function capitalizeFirst(text) {
  if (!text) return text
  const i = text.search(/\S/)
  if (i === -1) return text
  return text.slice(0, i) + text[i].toUpperCase() + text.slice(i + 1)
}

export function formatTitle(title) {
  return capitalizeFirst(macedonianize(title))
}
