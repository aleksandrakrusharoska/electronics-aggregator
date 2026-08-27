// Ad titles come from pazar3/reklama5 sellers typing in either script --
// proper Macedonian Cyrillic, "vernacular" Latin (no diacritics, e.g.
// "prodavam", "novo"), or diacritic Latin (č/š/ž). We normalize display to
// Cyrillic while leaving brand/model names (iPhone, PS5, RTX 4090...) in
// Latin, since transliterating those would be wrong, not just inconsistent.

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
  god: 'год', godini: 'години', mesec: 'месец', meseci: 'месеци',
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
  'ps3', 'ps4', 'ps5', 'ps2', 'switch', 'microsoft', 'google', 'logitech',
  'razer', 'corsair', 'benq', 'toshiba', 'panasonic', 'garmin', 'tp-link',
  'netgear', 'epson', 'brother', 'note', 'nord', 'fury', 'gddr', 'nvme',
  'windows', 'cpu', 'gpu',
])

function isBrandOrCode(word) {
  const bare = word.replace(/[^a-zA-Z0-9]/g, '')
  if (!bare) return false
  if (/\d/.test(bare)) return true // model numbers/codes: "4090", "13", "A54"
  // A known Macedonian dictionary word is never an acronym, whatever its
  // case -- without this, shouted short words like "NOV"/"ILI" (same
  // length as real acronyms GPU/TWS) get mistaken for one and skipped.
  if (WORD_MAP[bare.toLowerCase()]) return false
  // A lone letter is always a fragment of a part/model code ("Z890-F",
  // "USB-C", "M.2-512GB", "E-SIM") once split on -./ below, never a real
  // word by itself -- transliterating it turns "USB-C" into "USB-Ц".
  if (/^[a-zA-Z]$/.test(bare)) return true
  // Irregular internal capitalization (not all-lower, not all-upper, not
  // simple Title Case) reads as an acronym/spec fragment too -- "aRGB",
  // "mAh", "kWh" -- rather than a word we should transliterate.
  if (/[a-zA-Z]/.test(bare)) {
    const isAllLower = bare === bare.toLowerCase()
    const isAllUpper = bare === bare.toUpperCase()
    const isTitleCase = bare[0] === bare[0].toUpperCase() && bare.slice(1) === bare.slice(1).toLowerCase()
    if (!isAllLower && !isAllUpper && !isTitleCase) return true
  }
  // Short ALL-CAPS tokens (<=3 letters) read as acronyms (GPU, TWS, NFC).
  // Longer ALL-CAPS is usually just a seller shouting in Macedonian
  // ("AKTIVIRAN", "GARANCIA"), not an acronym -- let those fall through to
  // transliteration instead of getting stuck in Latin.
  if (bare.length > 1 && bare.length <= 3 && bare === bare.toUpperCase() && /[A-Z]/.test(bare)) return true
  return BRAND_WORDS.has(bare.toLowerCase())
}

// Common English marketing/tech adjectives that show up in ad titles and
// should stay in Latin rather than get letter-transliterated into gibberish
// ("gaming" -> "гаминг"). Same curated-list tradeoff as WORD_MAP/BRAND_WORDS
// above -- there's no real English-detector here, just a known-words list.
const ENGLISH_WORDS = new Set([
  'gaming', 'smart', 'pro', 'plus', 'mini', 'ultra', 'lite', 'edition',
  'series', 'model', 'version', 'style', 'design', 'sport', 'sports', 'fit',
  'active', 'turbo', 'boost', 'premium', 'deluxe', 'limited', 'special',
  'quality', 'slim', 'thin', 'light', 'mega', 'super', 'hyper', 'dual',
  'quad', 'full', 'micro', 'nano', 'auto', 'digital', 'portable', 'compact',
  'universal', 'noise', 'cancelling', 'sound', 'bass', 'stereo', 'mono',
  'hd', 'uhd', 'fhd', 'black', 'silver', 'gold', 'gray', 'grey', 'red',
  'blue', 'green', 'pink', 'purple', 'gen', 'set', 'kit', 'pack', 'bundle',
  'box', 'sealed', 'unused', 'top', 'best', 'hot', 'cool', 'deal', 'sale',
  'free', 'offer', 'price', 'cheap', 'warranty', 'unlocked', 'refurbished',
  'tested', 'working', 'functional', 'complete', 'extra', 'spare', 'backup',
  'official', 'certified', 'authentic', 'fashion', 'trend', 'trendy',
  'modern', 'classic', 'retro', 'vintage', 'link', 'mobile', 'phone',
])

// Letter-level fallback for plain-ASCII words that hit neither the
// dictionary nor the ENGLISH_WORDS list. Digraphs (including the diacritic
// "dž") checked before single letters so e.g. "sh" becomes "ш" rather than
// "с" + unmapped "h".
const LETTER_DIGRAPHS = [
  ['dž', 'џ'], ['Dž', 'Џ'], ['DŽ', 'Џ'],
  ['nj', 'њ'], ['Nj', 'Њ'], ['NJ', 'Њ'],
  ['lj', 'љ'], ['Lj', 'Љ'], ['LJ', 'Љ'],
  ['gj', 'ѓ'], ['Gj', 'Ѓ'], ['GJ', 'Ѓ'],
  ['kj', 'ќ'], ['Kj', 'Ќ'], ['KJ', 'Ќ'],
  ['dz', 'ѕ'], ['Dz', 'Ѕ'], ['DZ', 'Ѕ'],
  ['sh', 'ш'], ['Sh', 'Ш'], ['SH', 'Ш'],
  ['zh', 'ж'], ['Zh', 'Ж'], ['ZH', 'Ж'],
  ['ch', 'ч'], ['Ch', 'Ч'], ['CH', 'Ч'],
]

const LETTER_SINGLE = {
  a: 'а', b: 'б', v: 'в', g: 'г', d: 'д', e: 'е', z: 'з', i: 'и', j: 'ј',
  k: 'к', l: 'л', m: 'м', n: 'н', o: 'о', p: 'п', r: 'р', s: 'с', t: 'т',
  u: 'у', f: 'ф', h: 'х', c: 'ц',
  č: 'ч', š: 'ш', ž: 'ж', ć: 'ќ', đ: 'ѓ',
}

// bail: true rejects words containing q/w/x/y (not in the Macedonian
// alphabet -- usually a foreign/brand word). Diacritic words (č š ž ć đ)
// call this with bail:false since the diacritic already confirms it's
// Macedonian, so the rest of the word should still convert even if some
// other letter in it happens to be foreign.
function transliterateLetters(word, { bail = true } = {}) {
  if (bail && /[qwxy]/i.test(word)) return null
  let out = ''
  let i = 0
  while (i < word.length) {
    const digraph = LETTER_DIGRAPHS.find(([from]) => word.startsWith(from, i))
    if (digraph) {
      out += digraph[1]
      i += digraph[0].length
      continue
    }
    const ch = word[i]
    const cyr = LETTER_SINGLE[ch.toLowerCase()]
    out += cyr ? (ch === ch.toLowerCase() ? cyr : cyr.toUpperCase()) : ch
    i++
  }
  return out
}

// Word characters we transliterate over -- includes the diacritic Latin
// letters so e.g. "č" isn't treated as punctuation and stripped off.
const WORD_CHAR = /[a-zčšžćđ]/i

// Splits leading/trailing punctuation off a token so it survives whatever
// path transliterateCore takes below, instead of being dropped (a token
// like "kompjuter," used to lose its comma on a WORD_MAP match).
function splitAffixes(word) {
  let start = 0
  let end = word.length
  while (start < end && !WORD_CHAR.test(word[start])) start++
  while (end > start && !WORD_CHAR.test(word[end - 1])) end--
  return [word.slice(0, start), word.slice(start, end), word.slice(end)]
}

function transliterateCore(word) {
  const lower = word.toLowerCase()
  // Normalize stray accents (á, é, í...) some scraped titles pick up --
  // strip combining diacritics down to plain ASCII for the dictionary
  // lookup key only; the diacritic-preserving branch below still checks
  // the original word for real Macedonian digraphs (č š ž ć đ).
  const stripped = lower.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z]/g, '')
  if (WORD_MAP[stripped]) {
    const cyr = WORD_MAP[stripped]
    // Preserve the source's capitalization style: ALL CAPS stays ALL CAPS
    // ("NOV" -> "НОВ", a seller shouting), Title Case stays Title Case.
    if (word === word.toUpperCase() && /[a-zA-Z]/.test(word)) {
      return cyr.toUpperCase()
    }
    if (word[0] === word[0].toUpperCase() && /[a-zA-Z]/.test(word[0])) {
      return cyr[0].toUpperCase() + cyr.slice(1)
    }
    return cyr
  }
  // A Macedonian Latin diacritic (č š ž ć đ) anywhere in the word confirms
  // it's Macedonian, so convert the whole word letter-by-letter -- not just
  // the diacritic character itself ("sočuvan" -> "сочуван", not "soчuvan").
  if (/[čšžćđ]/i.test(word)) {
    return transliterateLetters(word, { bail: false })
  }
  // Known English word (see ENGLISH_WORDS) -- leave in Latin.
  if (ENGLISH_WORDS.has(stripped)) return word
  // Last resort: plain-ASCII letter substitution (see transliterateLetters).
  const letters = transliterateLetters(word)
  return letters !== null ? letters : word
}

function transliterateWord(word) {
  const [prefix, core, suffix] = splitAffixes(word)
  if (!core) return word
  return prefix + transliterateCore(core) + suffix
}

// Also split on runs of -./ (not just whitespace) so sellers who glue
// several words together without spaces ("2god.garanc.Telekom.MK",
// "--Novi--iBuyMobile") get each piece transliterated on its own, instead
// of one "poison" segment (a digit, or a q/w/x/y letter) blocking
// conversion of the whole glued blob. Reassembled losslessly since these
// delimiter tokens are kept as-is, same as whitespace.
const DELIMITER = /^[\s\-./]+$/

// A digit run glued directly to a word with no separator at all ("2god",
// "24meseci") would otherwise be swallowed whole by isBrandOrCode's digit
// rule (meant for codes like "4090"/"A54") and stay stuck in Latin. Only
// split it off when the letter part is a whole recognized word -- an
// unlisted unit suffix ("256gb", "5g", "100hz") must NOT split, since "gb"/
// "g"/"hz" alone would then get wrongly letter-transliterated.
function transliterateToken(tok) {
  const digitWord = tok.match(/^(\d+)([A-Za-zčšžćđ]+)$/i)
  if (digitWord) {
    const [, digits, letters] = digitWord
    const stripped = letters.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z]/g, '')
    if (WORD_MAP[stripped] || ENGLISH_WORDS.has(stripped)) {
      return digits + transliterateWord(letters)
    }
  }
  return isBrandOrCode(tok) ? tok : transliterateWord(tok)
}

export function macedonianize(text) {
  if (!text) return text
  return text
    .split(/(\s+|[-./]+)/)
    .map(tok => (DELIMITER.test(tok) ? tok : transliterateToken(tok)))
    .join('')
}

export function capitalizeFirst(text) {
  if (!text) return text
  const i = text.search(/\S/)
  if (i === -1) return text
  const firstWord = text.slice(i).match(/^\S+/)?.[0] ?? ''
  // Only skip a word that already has its OWN internal capitalization
  // ("iPhone", "eBay") -- forcing the first letter up would break that into
  // "IPhone". A plain lowercase brand word ("iphone", "samsung", "rtx") has
  // no such pattern to protect and should still get capitalized normally.
  if (/[A-ZА-Я]/.test(firstWord.slice(1))) return text
  return text.slice(0, i) + text[i].toUpperCase() + text.slice(i + 1)
}

export function formatTitle(title) {
  return capitalizeFirst(macedonianize(title))
}
