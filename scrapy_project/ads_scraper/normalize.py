import re
from datetime import date, datetime, timedelta, timezone

# North Macedonia pegs MKD to EUR at a stable rate
MKD_PER_EUR = 61.5

_MK_MONTHS = {
    'јан': 1, 'фев': 2, 'март': 3, 'апр': 4,
    'мај': 5, 'јун': 6, 'јул': 7, 'авг': 8,
    'септ': 9, 'окт': 10, 'ное': 11, 'дек': 12,
}

_DATE_RE = re.compile(r'^(\d{1,2})\s+([^\d]+?)\.*\s+(\d{1,2}:\d{2})$')
_RELATIVE_RE = re.compile(r'^(Денес|Вчера)\s+(\d{1,2}:\d{2})$', re.IGNORECASE)
# Detail page format: "мај 12 2015" or "мај 12 2015 02:22"
_DATE_FULL_RE = re.compile(r'^([^\d]+?)\s+(\d{1,2})\s+(\d{4})', re.IGNORECASE)

# Supplementary-plane emoji + common BMP symbol blocks
_EMOJI_RE = re.compile(
    '['
    '\U0001F300-\U0001FFFF'
    '\U00002600-\U000027BF'
    '\U0000FE00-\U0000FE0F'
    '\U00020000-\U0002FA1F'
    ']+',
    flags=re.UNICODE,
)

_CURRENCY_MAP = {
    '€': 'EUR', 'eur': 'EUR', 'EUR': 'EUR',
    'МКД': 'MKD', 'MKD': 'MKD', 'mkd': 'MKD',
    'ден': 'MKD', 'Ден': 'MKD', 'ден.': 'MKD',
}


def strip_emoji(text: str | None) -> str | None:
    if not text:
        return text
    return _EMOJI_RE.sub('', text).strip()


def clean_text(text: str | None) -> str | None:
    if not text:
        return text
    text = text.replace('\r\n', ' ').replace('\r', ' ').replace('\n', ' ')
    return re.sub(r'\s+', ' ', text).strip()


def clean_description(text: str | None) -> str | None:
    """Like clean_text, but for the full ad body rather than the title:
    keeps line breaks and emojis intact (sellers use both — bullet-point
    lists, section breaks) instead of flattening everything to one line.
    Only normalizes line endings, collapses runs of horizontal whitespace,
    and caps blank-line runs so excessive spacing doesn't blow up the layout.
    """
    if not text:
        return text
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def parse_price(raw: str | None) -> dict:
    """
    Parse a raw price string into structured fields.

    Returns a dict with:
      price_amount  str | None   clean numeric string with no separators, e.g. "2000"
      currency      str | None   "EUR" or "MKD"
      price_eur     float | None amount converted to EUR
      price_mkd     float | None amount converted to MKD
      price_note    str | None   original text when no numeric value found, e.g. "По Договор"
    """
    empty = {'price_amount': None, 'currency': None,
             'price_eur': None, 'price_mkd': None, 'price_note': None}
    if not raw:
        return empty

    raw = raw.replace('\r', ' ').replace('\n', ' ').strip()

    # Split into numeric part and trailing currency label
    m = re.match(r'^([\d\s.,]+)\s*(.*?)$', raw)
    if not m:
        return {**empty, 'price_note': raw}

    num_str = m.group(1).strip()
    currency_raw = m.group(2).strip()

    # Macedonian thousand separator is a dot ("2.000" = 2000).
    # Remove all dots and spaces, then treat comma as decimal separator.
    num_clean = re.sub(r'[\s.]', '', num_str).replace(',', '.')
    try:
        amount = float(num_clean)
    except ValueError:
        return {**empty, 'price_note': raw}

    currency = _CURRENCY_MAP.get(currency_raw)

    if currency == 'EUR':
        price_eur = round(amount, 2)
        price_mkd = round(amount * MKD_PER_EUR, 2)
    elif currency == 'MKD':
        price_mkd = round(amount, 2)
        price_eur = round(amount / MKD_PER_EUR, 2)
    else:
        price_eur = None
        price_mkd = None

    # Store amount as integer string when it has no fractional part
    price_amount = str(int(amount)) if amount == int(amount) else str(amount)

    return {
        'price_amount': price_amount,
        'currency': currency,
        'price_eur': price_eur,
        'price_mkd': price_mkd,
        'price_note': None,
    }


def resolve_posted_date(posted: str | None, scraped_at: str | None) -> str | None:
    """
    Convert pazar3 posted_date strings to ISO date (YYYY-MM-DD).

    Handles:
      "Денес HH:MM"   → scraped date
      "Вчера HH:MM"   → scraped date - 1 day
      "DD авг. HH:MM" → absolute date; year inferred from scraped_at
    """
    if not posted or not scraped_at:
        return None
    try:
        ref = datetime.fromisoformat(scraped_at.replace('Z', '+00:00'))
        ref_date = ref.date()
    except (ValueError, AttributeError):
        return None

    m_rel = _RELATIVE_RE.match(posted.strip())
    if m_rel:
        keyword = m_rel.group(1).lower()
        return ref_date.isoformat() if keyword == 'денес' else (ref_date - timedelta(days=1)).isoformat()

    m_abs = _DATE_RE.match(posted.strip())
    if m_abs:
        day = int(m_abs.group(1))
        month_key = m_abs.group(2).rstrip('.').strip().lower()
        month = _MK_MONTHS.get(month_key)
        if not month:
            return None
        year = ref_date.year
        if month > ref_date.month or (month == ref_date.month and day > ref_date.day):
            year -= 1
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None

    # Detail page format: "мај 12 2015" or "мај 12 2015 02:22"
    m_full = _DATE_FULL_RE.match(posted.strip())
    if m_full:
        month_key = m_full.group(1).rstrip('.').strip().lower()
        month = _MK_MONTHS.get(month_key)
        day = int(m_full.group(2))
        year = int(m_full.group(3))
        if month:
            try:
                return date(year, month, day).isoformat()
            except ValueError:
                return None

    return None
