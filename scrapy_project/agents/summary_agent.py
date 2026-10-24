"""Key-info summary ("Клучни инфо") for ads with a long description.

The parser extracts eleven fields per ad, several ads per request, and the
seller notes come last; asked for them that way the model mostly copied
the seller's sentences. Here one request covers one ad and only this line,
with the specs and condition the parser already found, so the summary
says what those don't. Tested on 60 ads (2026-10-19, no writes): verbatim
copies 19 -> 3, no all-caps, no mixed scripts.

Groq (gpt-oss-120b) only: Gemini, the parser's fallback, mixed Cyrillic
words into Latin-script summaries. When Groq is out of quota the parser's
own notes stay.
"""
import json
import logging
import re
from itertools import cycle

from agents.parser_agent import (RotatingParser, _extract_text, _mark_if_daily_exhausted, _notes_in_description_language,
                                 latin_script)
from agents.translit import to_latin_cased

logger = logging.getLogger(__name__)

MIN_DESCRIPTION = 200   # shorter descriptions need no summary: the notes would repeat them
MAX_NOTES = 180

SYSTEM = """You write the "key info" line of a Macedonian electronics classified ad: what a buyer should know that the
title, price, condition and specs shown next to it do not already say.

Include, most important first, only what the ad states:
1. warranty and how old the device is or where it was bought;
2. what comes with it or is missing (box, charger, case, controller, cables);
3. defects, repairs, battery health;
4. terms: exchange, instalments, delivery, cash only, testing before buying.

Leave out: anything already in the title or in the given specs/condition, the price and whether it is fixed or
negotiable, phone numbers, invitations to call or message, the location on its own, and sales talk ("top cena",
"perfekten", "odlicna sostojba").

Write one short line, at most 140 characters, in the SAME language AND script as the description: a Cyrillic
description gets Cyrillic, Macedonian written in Latin letters gets Latin letters, English gets English. Write
Macedonian, not Serbian or Croatian ("doagja", "licno prezemanje", "isprakjam", not "dolazi", "lično preuzimanje",
"šaljem"). Normal capitalisation even if the seller writes in capitals; keep model names as written. If nothing is
left after the rules above, answer null.

Answer only JSON: {"notes": "..."} or {"notes": null}.

Examples:
Description: "Се продава Samsung A36 5G користен три месеци. Одлично е сочуван, има гаранција уште 10 месеци. Телефони за контакт 070 280 181"
Specs: {} Condition: Used - Like New
{"notes": "Користен три месеци, гаранција уште 10 месеци."}

Description: "Iphone 15 128GB 6/128, Koristen Kako Nov, Fabricno Sve Neotvaran Nikogas BH77% Face ID-ok Sledi Mag Safe Maska, Hidro Gel Folija Na Ekran, Nov Fast Polnac 20watti!! Bez Zameni!!"
Specs: {"storage": "128GB", "battery": "77%"} Condition: Used - Like New
{"notes": "Nikogas otvoran, se dobivaat MagSafe maska, hidrogel folija i nov polnac 20W. Bez zameni."}

Description: "Prodavam asus rog g752 lap top e odlicen ne koristen za gaming koristen samo vo domasni uslovi baterija drzi licenciran windows 10 konatakt samo na email viber"
Specs: {} Condition: Used - Good
{"notes": "Koristen samo doma, baterijata drzi, licenciran Windows 10."}

Description: "Продавам iPhone 13 128GB, батерија 85%, многу сочуван. Цена 300 евра. Скопје, Аеродром."
Specs: {"storage": "128GB", "battery": "85%"} Condition: Used - Good
{"notes": null}"""

_CONTACT = re.compile(r"(\d{3}[- /]?\d{3}[- ]?\d{3}|viber|javete|јавете|pisete|пишете|povekje info|повеќе инфо)", re.I)
_WORD = re.compile(r"[^\W_]+")
_PUNCT = {"‑": "-", "–": ",", "—": ",", " ": " ", " ": " "}

_UNSET = object()   # the summary call failed: keep the parser's notes
_REJECTED = object()   # the model wrote Serbian/Croatian twice: keep the old notes, try another day

# The model sometimes slips into Serbian/Croatian (2026-10-22: 18 of 455
# summaries, "Korišten samo 2 meseci", "dolazi so monitor, miš"). Letters and
# words a Macedonian seller doesn't write; only rejected when the
# description doesn't have them itself (some sellers do type "č").
_SERBIAN_LETTERS = re.compile(r"[šžčćđ]", re.I)
_SERBIAN_WORDS = re.compile(r"\b(dolazi|dolaze|korišten\w*|koriscen\w*|korišćen\w*|uključen\w*|ukljucen\w*|punjač\w*|"
                            r"preuzimanje|šaljem|saljem|švajcarsk\w*|svajcarsk\w*|instalirane|garancijom|kutijom|"
                            r"долази|коришћен\w*|укључен\w*|пуњач\w*|преузимање|шаљем)\b", re.I)
# "Fixed price" is about the price, which the prompt leaves out (37 of 455)
_FIXED_PRICE = re.compile(r"\b(cenata e fiksna|cena(ta)? (e )?fiksna|fiksna cena|fiksno|"
                          r"цената е фиксна|цена(та)? (е )?фиксна|фиксна цена|фиксно)\b\.?", re.I)


def _serbian(notes: str, description: str) -> bool:
    for rx in (_SERBIAN_LETTERS, _SERBIAN_WORDS):
        if rx.search(notes) and not rx.search(description):
            return True
    return False


def _without_fixed_price(notes: str) -> str:
    if not _FIXED_PRICE.search(notes):
        return notes
    notes = _FIXED_PRICE.sub("", notes)
    notes = re.sub(r"\s*([,;])\s*(?=[,;.]|$)", "", notes)      # separators left before another or at the end
    notes = re.sub(r"\s{2,}", " ", notes).strip(" ,;")
    return notes if notes.endswith(".") or not notes else notes + "."


def _recase(notes: str) -> str:
    """"BEZ ZAMENI SAMO KES." -> "Bez zameni samo kes." (the prompt asks for
    normal capitalisation; all-caps summaries stayed bad and were retried)."""
    letters = [c for c in notes if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) > 0.6 * len(letters):
        notes = notes.lower()
        notes = notes[:1].upper() + notes[1:]
    return notes


def needs_summary(description: str | None) -> bool:
    return len(description or "") >= MIN_DESCRIPTION


def build_summary_clients(parser: RotatingParser) -> RotatingParser:
    """The parser's rotation reduced to its Groq keys (a shallow copy)."""
    groq = RotatingParser.__new__(RotatingParser)
    groq._clients = [(n, c) for n, c in parser._clients if n.startswith("groq")]
    groq._cycle = cycle(groq._clients)
    groq._exhausted = set()
    return groq


def clean_summary(notes, title: str, description: str) -> str | None:
    """Model output -> what is stored, or None when it breaks the rules."""
    if not notes or not isinstance(notes, str):
        return None
    notes = notes.strip()
    for a, b in _PUNCT.items():
        notes = notes.replace(a, b)
    if latin_script(description):
        notes = to_latin_cased(notes)   # no Cyrillic words inside a Latin-script note
    notes = _notes_in_description_language(notes, description)
    if notes:
        notes = _recase(_without_fixed_price(notes))
    if not notes or _CONTACT.search(notes) or len(notes) > MAX_NOTES:
        return None
    note_words = set(_WORD.findall(notes.lower()))
    if note_words and len(note_words - set(_WORD.findall((title or "").lower()))) <= 1:
        return None   # nothing beyond the title
    return notes


def summarise(clients: RotatingParser, title: str, description: str, specs: dict | None, condition: str | None):
    """The key-info line for one ad: a string, None (nothing worth saying),
    _UNSET when no Groq key could answer, or _REJECTED when the model wrote
    Serbian/Croatian on two tries."""
    user = (f'Title: "{title}"\nDescription: "{description}"\n'
            f'Specs: {json.dumps(specs or {}, ensure_ascii=False)} Condition: {condition}')
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
    serbian_tries = 0
    for _ in range(len(clients._clients)):
        try:
            name, client = clients.next()
        except Exception:
            return _UNSET
        try:
            raw = _extract_text(client.invoke(messages).content).strip()
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
            notes = clean_summary(json.loads(raw).get("notes"), title, description)
            if notes and _serbian(notes, description):
                serbian_tries += 1
                logger.info("Summary in Serbian/Croatian, %s: %r", "rejected" if serbian_tries == 2 else "retrying", notes)
                if serbian_tries == 2:
                    return _REJECTED
                continue
            return notes
        except Exception as exc:
            # Only the daily limit takes a key out; the per-minute one (8,000
            # tokens, about five summaries) did too until 2026-10-23 and
            # stopped resummarise_notes after 149 ads with the day's quota unused
            if not _mark_if_daily_exhausted(clients, name, exc):
                logger.warning("Summary via %s failed: %s", name, str(exc)[:200])
    return _UNSET


def apply_summary(clients: RotatingParser, title: str, description: str, parsed) -> None:
    """Replace parsed.seller_notes with the summary for a long description."""
    if not needs_summary(description) or not clients._clients:
        return
    notes = summarise(clients, title, description, parsed.specs, parsed.condition)
    if notes is not _UNSET and notes is not _REJECTED:
        parsed.seller_notes = notes
