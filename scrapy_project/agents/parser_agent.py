"""
LLM-based parser for unstructured electronics ad descriptions.
Rotates across Groq (openai/gpt-oss-20b) and Gemini API keys on each
request to share the load across their free-tier daily token limits.

openai/gpt-oss-20b, despite being a reasoning model, is the pick by
elimination: Groq deprecated llama-3.1-8b-instant and llama-3.3-70b-versatile
on 2026-06-01 (confirmed live against /v1/models — both 404 now), and
Groq's own migration guidance for the retired 8b-instant points at
gpt-oss-20b/120b. Measured directly against real ad descriptions from
this table, actual cost is ~1,800 tokens/call average (not the ~10k
naively implied by dividing a day's exhaustion count into 200k TPD —
see reasoning_effort='low' below and the GROQ_MODEL override for tuning
this further if a better non-reasoning option reappears).
"""
import json
import logging
import os
import re
from itertools import cycle
from typing import Dict, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_RULES = """- ONLY extract information EXPLICITLY written in the title/description. Do NOT invent or guess.
- specs: key-value pairs of technical specs (RAM, storage, display, battery, processor, etc.) found in the text. Empty object if none mentioned.
- condition: ONLY if explicitly mentioned or clearly implied by words like "nov"/"нов" (new), "zachuvan"/"odlicna sostojba" (well-kept), "koristen"/"користено" (used), "za delovi" (for parts). One of:
  "New" — brand new, unused, sealed/unopened.
  "Used - Like New" — used but pristine, no visible wear, barely used.
  "Used - Good" — used, functional, normal minor cosmetic wear.
  "Used - Fair" — used, noticeable wear/damage but still functional.
  "Used" — clearly used, but the text doesn't say enough to pick Like New/Good/Fair.
  "For parts" — broken/non-functional, sold for parts or repair only.
  If genuinely unclear, use null. Never put condition inside specs.
- brand: the manufacturer, normalized to its common English name (e.g. "Apple", "Samsung", "Huawei", "Xiaomi"). null if not identifiable.
- model: the specific model name/number, normalized to how it's commonly written, WITHOUT storage/color/condition/network words (e.g. "iPhone 11", "Galaxy S20+", "Galaxy A35 5G", "P30 Pro"). null if not identifiable.
- seller_notes: seller personal comments (warranty, reason for selling, meeting/delivery place, a functional defect or caveat like battery health/stick drift/a crack, what extra accessories/items are included or missing). Do NOT use this for routine cosmetic condition talk (e.g. "добра состојба", "исчистена", a sticker/skin/decoration that doesn't affect function) — that's normal description filler, not personal commentary. Write it in the SAME language the ad's title/description is written in — do NOT translate it to English. null if none.
- phone: first phone number found (Macedonian numbers start with 07, 02, 03). null if none.
- delivery_available: true only if seller explicitly mentions delivery/shipping, otherwise false.
- seller_type: "private" or "business". null if unclear.
- is_electronics: true if the item itself is an electronic/tech product (phones, computers, game consoles, TVs, cameras, audio gear, electric scooters, VR headsets, drones, etc.) or a part/accessory for one. false for anything else — sporting goods, board games, billiard/dart/foosball tables, plush toys, furniture, etc. — even if it was listed under an electronics category. If genuinely ambiguous, use true (don't hide things you're unsure about).
- If the item is not electronics, still fill in whatever fields are genuinely stated (e.g. condition), just set is_electronics to false — don't blank everything out.
- stated_price_amount / stated_price_currency: sellers sometimes type the price again inside the description text (e.g. "CENA 300 EVRA", "цена: 15000 ден"), separately from the ad's own price field, and the two can disagree (a currency mix-up, a typo). ONLY fill these if the description itself explicitly states a price with a number and a currency — extract the number as stated_price_amount and the currency as stated_price_currency, exactly "EUR" or "MKD" (den/denari/мкд all mean MKD; evra/eur/€ all mean EUR). null/null if the description doesn't explicitly restate a price."""

_SYSTEM = f"""You extract structured information from second-hand electronics ads.
Ads may be written in Macedonian, Albanian, Serbian, or English.
Return ONLY a valid JSON object — no markdown, no code blocks, no explanation.

CRITICAL RULES:
{_RULES}

Return exactly this structure:
{{"specs": {{}}, "condition": null, "brand": null, "model": null, "seller_notes": null, "phone": null, "delivery_available": false, "seller_type": null, "is_electronics": true, "stated_price_amount": null, "stated_price_currency": null}}"""

# Batched variant: N ads in one call instead of one call per ad, so the
# ~1000-token system prompt above (over half the cost of a single-ad call,
# measured against real ad text) is paid once per batch instead of once per
# ad. Each input/output item carries its own "i" index rather than relying
# on response order matching request order, since a dropped or reordered
# array element would otherwise silently mismatch an ad to the wrong result.
_SYSTEM_BATCH = f"""You extract structured information from multiple second-hand electronics ads at once.
Ads may be written in Macedonian, Albanian, Serbian, or English.
You will receive a JSON array where each element has "i" (an integer index) and "title"/"description" for one ad.
Return ONLY a valid JSON array — no markdown, no code blocks, no explanation — with exactly one object per input ad, in the same order, each carrying its original "i" plus the extracted fields below.

CRITICAL RULES (apply independently to each ad — do not let one ad's content influence another's):
{_RULES}

Each output array element must have exactly this structure:
{{"i": 0, "specs": {{}}, "condition": null, "brand": null, "model": null, "seller_notes": null, "phone": null, "delivery_available": false, "seller_type": null, "is_electronics": true, "stated_price_amount": null, "stated_price_currency": null}}"""


class ParsedAdContent(BaseModel):
    specs: Dict[str, str] = Field(default_factory=dict)
    condition: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    seller_notes: Optional[str] = None
    phone: Optional[str] = None
    delivery_available: bool = False
    seller_type: Optional[str] = None
    is_electronics: bool = True
    stated_price_amount: Optional[float] = None
    stated_price_currency: Optional[str] = None


def _build_clients():
    """Build all available LLM clients. Returns a list of (name, client) tuples."""
    clients = []
    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

    from langchain_groq import ChatGroq
    # reasoning_effort='low' cuts gpt-oss-20b's hidden chain-of-thought
    # token spend without hurting this task's output quality — measured
    # directly (real system prompt + real ad text): completion tokens drop
    # ~40% (e.g. 353->209 on one sample) at 'low' vs the default 'medium',
    # with no change to prompt tokens or output correctness.
    reasoning_effort = os.getenv("GROQ_REASONING_EFFORT", "low")
    # Headroom above the current key count so adding another key later only
    # needs a new secret + .env line in the workflow, not a code change here.
    groq_vars = ["GROQ_API_KEY"] + [f"GROQ_API_KEY_{n}" for n in range(2, 21)]
    for i, var in enumerate(groq_vars):
        key = os.getenv(var)
        if key:
            name = "groq" if i == 0 else f"groq{i + 1}"
            clients.append((name, ChatGroq(
                model=model, api_key=key, temperature=0,
                reasoning_effort=reasoning_effort,
            )))

    from langchain_google_genai import ChatGoogleGenerativeAI
    # gemini-2.0-flash (the model previously used here) was shut down by
    # Google on 2026-06-01, and gemini-2.5-flash-lite is no longer
    # available to new API keys either (both 404 NOT_FOUND; Google's own
    # error message points new callers at 3.5). Flash-Lite is the current
    # free-tier model with the highest daily quota, which is what this
    # rotation actually needs (plain structured-JSON extraction, not
    # complex reasoning).
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    for i, var in enumerate(["GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3"]):
        key = os.getenv(var)
        if key:
            name = "gemini" if i == 0 else f"gemini{i + 1}"
            clients.append((name, ChatGoogleGenerativeAI(model=gemini_model, google_api_key=key, temperature=0)))

    if not clients:
        raise RuntimeError("No LLM API keys found. Set GROQ_API_KEY and/or GEMINI_API_KEY.")

    logger.info("Parser using %d provider(s): %s", len(clients), [n for n, _ in clients])
    return clients


class AllProvidersExhausted(Exception):
    """Raised when every configured LLM provider has hit its daily limit."""


class RotatingParser:
    """Alternates requests between all available LLM providers."""

    def __init__(self):
        self._clients = _build_clients()
        self._cycle = cycle(self._clients)
        self._exhausted: set = set()

    def next(self):
        for _ in range(len(self._clients)):
            name, client = next(self._cycle)
            if name not in self._exhausted:
                return name, client
        raise AllProvidersExhausted("All LLM providers exhausted for this run.")

    def mark_exhausted(self, name: str):
        self._exhausted.add(name)
        remaining = [n for n, _ in self._clients if n not in self._exhausted]
        logger.warning("Provider '%s' hit daily limit — removed from rotation. Remaining: %s", name, remaining)


def build_parser() -> RotatingParser:
    return RotatingParser()


# Accessory concepts the parser has been observed inventing as "included" in
# seller_notes even when the ad text never mentions them — a hallucination
# failure mode, not a formatting quirk (seen with the smaller/faster models
# in this rotation). seller_notes is often translated to English regardless
# of the ad's own language, so each concept lists its Macedonian (Cyrillic
# and Latin transliteration), Albanian, and English spellings — checking a
# single keyword string across languages produced near-100% false positives
# (e.g. notes saying "box" against source text that says "кутија").
# Deliberately excludes case/cover words (футрола, maska, cover...): those
# are the most commonly and legitimately mentioned item, and conflating
# them with cable/charger would just reintroduce false positives.
_ACCESSORY_CONCEPTS = {
    'cable': ['кабел', 'kabel', 'kabl', 'kabli', 'cable'],
    'charger': ['полнач', 'polnac', 'пуњач', 'punjac', 'karikues', 'charger', 'адаптер', 'adapter'],
    'box': ['кутија', 'kutija', 'kuti', 'box'],
    'earphones': ['слушалки', 'слушалќи', 'slusalki', 'slusalice', 'kufje', 'earphones', 'headphones'],
    'screen protector': ['фолија', 'folija', 'стакло', 'staklo', 'xham', 'screen protector', 'tempered glass'],
}


def _strip_unverified_accessory_claims(notes: str | None, source_text: str) -> str | None:
    """Drop seller_notes claiming an included accessory (cable, charger,
    box, etc.) that isn't actually mentioned anywhere in the ad's own
    title/description, in any of the languages/scripts it might appear in.
    This is a hallucinated claim, not a phrasing issue, so the safe move is
    to drop the whole note rather than try to surgically edit out just the
    invented part.
    """
    if not notes:
        return notes
    notes_l = notes.lower()
    source_l = (source_text or '').lower()
    for concept, synonyms in _ACCESSORY_CONCEPTS.items():
        claimed = any(syn in notes_l for syn in synonyms)
        confirmed = any(syn in source_l for syn in synonyms)
        if claimed and not confirmed:
            logger.warning("Dropping seller_notes with unverified %s claim: %r", concept, notes)
            return None
    return notes


# Fields the model occasionally nests inside "specs" instead of emitting as
# siblings (it conflates the output schema with actual spec key-value pairs)
# — seen paired with a truncated response missing its final closing brace,
# since everything after "specs" ends up one nesting level too deep.
_SCHEMA_KEYS_MISNESTED_IN_SPECS = {
    "condition", "brand", "model", "seller_notes", "phone",
    "delivery_available", "seller_type", "is_electronics",
    "stated_price_amount", "stated_price_currency",
}


def _coerce_float(value) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(re.sub(r'[^\d.]', '', value.replace(',', '.')))
        except ValueError:
            return None
    return None


def _parse_json_response(raw: str) -> dict:
    """Parse the model's JSON, repairing the truncated-nested-object
    malformation described above when a straight parse fails."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        opens, closes = raw.count('{'), raw.count('}')
        if opens <= closes:
            raise
        data = json.loads(raw + '}' * (opens - closes))

    specs = data.get("specs")
    if isinstance(specs, dict):
        for key in _SCHEMA_KEYS_MISNESTED_IN_SPECS & specs.keys():
            if key not in data:
                data[key] = specs.pop(key)
    return data


def _parse_json_array_response(raw: str) -> list:
    """Parse the model's JSON array, repairing a response truncated
    mid-element (the array analogue of _parse_json_response's brace repair
    above) when a straight parse fails."""
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    opens_c, closes_c = raw.count('{'), raw.count('}')
    opens_b, closes_b = raw.count('['), raw.count(']')
    patched = raw + '}' * max(0, opens_c - closes_c) + ']' * max(0, opens_b - closes_b)
    try:
        data = json.loads(patched)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    # Last resort: the tail element itself is unrecoverably truncated —
    # cut back to the last complete "}," element boundary and close the
    # array there, dropping just that one item instead of the whole batch.
    cut = raw.rfind('},')
    if cut != -1:
        data = json.loads(raw[:cut + 1] + ']')
        if isinstance(data, list):
            return data
    raise ValueError(f"Could not parse JSON array from: {raw[:200]!r}")


def _content_from_data(data: dict, title: str, description: str) -> ParsedAdContent:
    """Build a ParsedAdContent from one already-parsed JSON object, applying
    the same post-processing (accessory-claim stripping, price-currency
    validation) regardless of whether it came from a single-ad or batched
    LLM response."""
    source_text = f"{title or ''} {description or ''}"
    seller_notes = _strip_unverified_accessory_claims(data.get("seller_notes") or None, source_text)
    stated_currency = data.get("stated_price_currency")
    stated_currency = stated_currency.strip().upper() if isinstance(stated_currency, str) else None
    if stated_currency not in ("EUR", "MKD"):
        stated_currency = None
    stated_amount = _coerce_float(data.get("stated_price_amount"))
    if stated_amount is None or stated_amount <= 0:
        stated_currency = None

    return ParsedAdContent(
        specs={k: str(v) for k, v in (data.get("specs") or {}).items() if v and str(v).strip()},
        condition=data.get("condition") or None,
        brand=data.get("brand") or None,
        model=data.get("model") or None,
        seller_notes=seller_notes,
        phone=data.get("phone") or None,
        delivery_available=bool(data.get("delivery_available", False)),
        seller_type=data.get("seller_type") or None,
        is_electronics=bool(data.get("is_electronics", True)),
        stated_price_amount=stated_amount if stated_currency else None,
        stated_price_currency=stated_currency,
    )


def _extract_text(content) -> str:
    """Normalize a LangChain message's .content to plain text. ChatGroq
    returns a str; newer ChatGoogleGenerativeAI versions return a list of
    content blocks (e.g. [{'type': 'text', 'text': '...'}]) instead."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get('type') == 'text':
                parts.append(block.get('text', ''))
        return ''.join(parts)
    return str(content)


def parse_ad(title: str, description: str, parser: RotatingParser = None) -> ParsedAdContent:
    if parser is None:
        parser = build_parser()

    prompt = f"Title: {(title or '').strip()}\n\nDescription:\n{(description or '').strip()}"
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": prompt},
    ]

    for _ in range(len(parser._clients)):
        name, client = parser.next()
        try:
            response = client.invoke(messages)
            raw = _extract_text(response.content).strip()
            raw = re.sub(r'^```(?:json)?\s*', '', raw)
            raw = re.sub(r'\s*```$', '', raw)
            data = _parse_json_response(raw)
            logger.debug("Parsed via %s: %s", name, title[:50])
            return _content_from_data(data, title, description)
        except Exception as exc:
            if _mark_if_daily_exhausted(parser, name, exc):
                pass
            else:
                logger.warning("LLM parse failed (%s) for title=%r: %s — trying next provider", name, title, exc)

    logger.error("All providers exhausted or failed for title=%r", title)
    return ParsedAdContent()


def _mark_if_daily_exhausted(parser: RotatingParser, name: str, exc: Exception) -> bool:
    """Gemini's daily-quota error uses "RESOURCE_EXHAUSTED" + a PerDay/
    limit:0 marker; Groq's uses "tokens per day (TPD)". Only these
    daily-limit cases should permanently drop the provider from rotation
    for the rest of the run — a transient per-minute rate limit should
    just fall through to the next provider for this one call, not disable
    it entirely. Returns whether the provider was marked exhausted."""
    exc_str = str(exc)
    is_daily_exhausted = (
        'RESOURCE_EXHAUSTED' in exc_str and ('PerDay' in exc_str or 'per_day' in exc_str or 'limit: 0' in exc_str)
    ) or 'per day (TPD)' in exc_str
    if is_daily_exhausted:
        parser.mark_exhausted(name)
    return is_daily_exhausted


def parse_ads_batch(items: list[tuple[str, str]], parser: RotatingParser = None) -> list[ParsedAdContent]:
    """Parse multiple (title, description) ads in a single LLM call,
    amortizing the system prompt's fixed token cost across the whole batch
    instead of paying it once per ad. Returns results in the same order as
    items — a batch this small (see PARSE_BATCH_SIZE) practically never
    needs the per-index realignment below, but it's there so one dropped
    element degrades to a single missing result instead of desyncing every
    ad after it."""
    if parser is None:
        parser = build_parser()
    if not items:
        return []

    payload = [
        {"i": i, "title": (title or '').strip(), "description": (description or '').strip()}
        for i, (title, description) in enumerate(items)
    ]
    messages = [
        {"role": "system", "content": _SYSTEM_BATCH},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]

    for _ in range(len(parser._clients)):
        name, client = parser.next()
        try:
            response = client.invoke(messages)
            raw = _extract_text(response.content).strip()
            raw = re.sub(r'^```(?:json)?\s*', '', raw)
            raw = re.sub(r'\s*```$', '', raw)
            results_raw = _parse_json_array_response(raw)

            by_index = {}
            for entry in results_raw:
                if isinstance(entry, dict) and isinstance(entry.get("i"), int):
                    by_index[entry["i"]] = entry

            parsed_list = []
            for i, (title, description) in enumerate(items):
                data = by_index.get(i)
                if data is None:
                    logger.warning("Batch response missing index %d (title=%r) — defaulting to empty result", i, title)
                    parsed_list.append(ParsedAdContent())
                else:
                    parsed_list.append(_content_from_data(data, title, description))

            logger.debug("Parsed batch of %d via %s", len(items), name)
            return parsed_list
        except Exception as exc:
            if not _mark_if_daily_exhausted(parser, name, exc):
                logger.warning("LLM batch parse failed (%s) for %d ads: %s — trying next provider", name, len(items), exc)

    logger.error("All providers exhausted or failed for batch of %d ads", len(items))
    return [ParsedAdContent() for _ in items]
