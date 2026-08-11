"""
LLM-based parser for unstructured electronics ad descriptions.
Rotates between Groq (llama-3.1-8b-instant) and Gemini (gemini-2.0-flash)
on each request to share the load across both free-tier daily token limits.
"""
import json
import logging
import os
import re
from itertools import cycle
from typing import Dict, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_SYSTEM = """You extract structured information from second-hand electronics ads.
Ads may be written in Macedonian, Albanian, Serbian, or English.
Return ONLY a valid JSON object — no markdown, no code blocks, no explanation.

CRITICAL RULES:
- ONLY extract information EXPLICITLY written in the title/description. Do NOT invent or guess.
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
- seller_notes: seller personal comments (warranty, reason for selling, meeting place). null if none.
- phone: first phone number found (Macedonian numbers start with 07, 02, 03). null if none.
- delivery_available: true only if seller explicitly mentions delivery/shipping, otherwise false.
- seller_type: "private" or "business". null if unclear.
- is_electronics: true if the item itself is an electronic/tech product (phones, computers, game consoles, TVs, cameras, audio gear, electric scooters, VR headsets, drones, etc.) or a part/accessory for one. false for anything else — sporting goods, board games, billiard/dart/foosball tables, plush toys, furniture, etc. — even if it was listed under an electronics category. If genuinely ambiguous, use true (don't hide things you're unsure about).
- If the item is not electronics, still fill in whatever fields are genuinely stated (e.g. condition), just set is_electronics to false — don't blank everything out.

Return exactly this structure:
{"specs": {}, "condition": null, "brand": null, "model": null, "seller_notes": null, "phone": null, "delivery_available": false, "seller_type": null, "is_electronics": true}"""


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


def _build_clients():
    """Build all available LLM clients. Returns a list of (name, client) tuples."""
    clients = []
    model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

    from langchain_groq import ChatGroq
    groq_vars = ["GROQ_API_KEY"] + [f"GROQ_API_KEY_{n}" for n in range(2, 7)]
    for i, var in enumerate(groq_vars):
        key = os.getenv(var)
        if key:
            name = "groq" if i == 0 else f"groq{i + 1}"
            clients.append((name, ChatGroq(model=model, api_key=key, temperature=0)))

    from langchain_google_genai import ChatGoogleGenerativeAI
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
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
            raw = response.content.strip()
            raw = re.sub(r'^```(?:json)?\s*', '', raw)
            raw = re.sub(r'\s*```$', '', raw)
            data = json.loads(raw)
            logger.debug("Parsed via %s: %s", name, title[:50])
            source_text = f"{title or ''} {description or ''}"
            seller_notes = _strip_unverified_accessory_claims(data.get("seller_notes") or None, source_text)
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
            )
        except Exception as exc:
            exc_str = str(exc)
            # Gemini's daily-quota error uses "RESOURCE_EXHAUSTED" + a
            # PerDay/limit:0 marker; Groq's uses "tokens per day (TPD)".
            # Only these daily-limit cases should permanently drop the
            # provider from rotation for the rest of the run — a transient
            # per-minute rate limit should just fall through to the next
            # provider for this one call, not disable it entirely.
            is_daily_exhausted = (
                'RESOURCE_EXHAUSTED' in exc_str and ('PerDay' in exc_str or 'per_day' in exc_str or 'limit: 0' in exc_str)
            ) or 'per day (TPD)' in exc_str
            if is_daily_exhausted:
                parser.mark_exhausted(name)
            else:
                logger.warning("LLM parse failed (%s) for title=%r: %s — trying next provider", name, title, exc)

    logger.error("All providers exhausted or failed for title=%r", title)
    return ParsedAdContent()
