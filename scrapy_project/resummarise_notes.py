"""One-off: clean up the key info ("Клучни инфо") of ads parsed before the
summary step (agents/summary_agent.py, 2026-10-19).

An active ad's notes count as bad when they are shown in the app (the
frontend hides notes that just repeat a short description) and they are in
English or the wrong script, carry a phone number or "call me", are in
capitals, or are a long sentence copied from the description. The audit on
2026-10-19 found 2,705 such ads out of 13,390 with notes.

  long description (200+ characters): a new summary (Groq, one call each)
  short description: the notes are cleared, there is nothing to summarise

Only ad_analysis.seller_notes is written. Stops by itself when Groq is out
of quota; run again the next day and it picks up where it stopped, since a
fixed ad no longer counts as bad.

Usage:
    python resummarise_notes.py --dry-run --limit 30      # print, no writes
    python resummarise_notes.py --limit 500                # one day's share
"""
import argparse
import logging
import os
import random
import re
import time

from dotenv import load_dotenv
from supabase import create_client

from agents.parser_agent import build_parser, latin_script
from agents.summary_agent import _UNSET, build_summary_clients, needs_summary, summarise

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s", datefmt="%H:%M:%S")
for noisy in ("httpx", "httpcore"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
log = logging.getLogger(__name__)

_EN = re.compile(r"\b(the|and|with|only|warranty|months?|included|includes|packaging|works|delivery|charger|comes|original box)\b", re.I)
_CONTACT = re.compile(r"(\d{3}[- /]?\d{3}[- ]?\d{3}|viber|javete|јавете|pisete|пишете|povekje info|повеќе инфо|kontakt|контакт)", re.I)
_WORD = re.compile(r"[^\W_]+")
# A price ("CENA 190 EVRA", "7500den", "300 €"): the app shows the price already
_PRICE = re.compile(r"\b(cena|цена)\b|\d[\d.,]*\s*(€|(eur|euro|evra|evro|ден|денари|den|denari|мкд|mkd)\b)", re.I)


def _script(text):
    return "lat" if latin_script(text) else "cyr"


def _caps(text):
    return sum(c.isupper() for c in text) > 0.6 * max(1, sum(c.isalpha() for c in text))


def is_bad(notes: str, description: str) -> bool:
    """Shown in the app (same rule as AdModal.jsx) and bad."""
    nw, dw = _WORD.findall(notes.lower()), _WORD.findall(description.lower())
    if nw and sum(w in set(dw) for w in nw) / len(nw) >= 0.85 and len(nw) >= 0.5 * len(dw):
        return False   # hidden in the app anyway
    if _EN.search(notes) and not _EN.search(description):
        return True
    if _script(notes) != _script(description) or _CONTACT.search(notes) or _caps(notes):
        return True
    return len(notes) > 60 and notes.strip().lower().rstrip(".!") in description.lower()


def short_fix(notes: str, description: str) -> str | None:
    """Notes of an ad with a short description: no LLM. Notes that are only
    in capitals keep their content ("GARANCIA 2 GODINI" -> "Garancia 2
    godini"); anything else bad (English, wrong script, a contact, a
    price) goes."""
    english = _EN.search(notes) and not _EN.search(description)
    if english or _script(notes) != _script(description) or _CONTACT.search(notes) or _PRICE.search(notes) \
            or not _caps(notes):
        return None
    text = notes.strip().lower()
    return text[:1].upper() + text[1:]


def _page(sb, table, cols, filt=lambda q: q):
    out, last = [], ""
    while True:
        batch = filt(sb.table(table).select(cols)).gt("ad_url", last).order("ad_url").limit(1000).execute().data
        out += batch
        if len(batch) < 1000:
            return out
        last = batch[-1]["ad_url"]


def find_bad(sb):
    notes = _page(sb, "ad_analysis", "ad_url,seller_notes,is_electronics", lambda q: q.not_.is_("seller_notes", "null"))
    ads = {a["ad_url"]: a for a in _page(sb, "ads", "ad_url,title,description,specs,condition,is_active")}
    bad = []
    for n in notes:
        ad = ads.get(n["ad_url"])
        if not ad or ad.get("is_active") is False or not ad.get("description"):
            continue
        if n.get("is_electronics") is False:
            continue   # cars, flats...: the app does not show them
        if is_bad(n["seller_notes"], ad["description"]):
            bad.append({**ad, "seller_notes": n["seller_notes"]})
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="max ads to re-summarise (LLM calls)")
    args = ap.parse_args()

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    bad = find_bad(sb)
    long_ads = [a for a in bad if needs_summary(a["description"])]
    short_ads = [a for a in bad if not needs_summary(a["description"])]
    log.info("Bad key info on %d active ads: %d to re-summarise, %d to clear", len(bad), len(long_ads), len(short_ads))
    if args.dry_run:
        random.seed(11)
        long_ads = random.sample(long_ads, min(args.limit or 30, len(long_ads)))
        short_ads = random.sample(short_ads, min(10, len(short_ads)))
    elif args.limit is not None:
        long_ads = long_ads[:args.limit]

    clients = build_summary_clients(build_parser())
    done = cleared = kept = 0
    for ad in long_ads:
        new = summarise(clients, ad["title"] or "", ad["description"], ad.get("specs"), ad.get("condition"))
        if new is _UNSET:
            log.warning("Groq is out of quota: stopping after %d ads; run again tomorrow.", done)
            break
        if args.dry_run:
            print(f"# {(ad['title'] or '')[:70]}\n   BEFORE: {ad['seller_notes'][:160]!r}\n   AFTER : {new!r}")
        else:
            sb.table("ad_analysis").update({"seller_notes": new}).eq("ad_url", ad["ad_url"]).execute()
        done += 1
        time.sleep(0.5)
    for ad in short_ads:
        new = short_fix(ad["seller_notes"], ad["description"])
        if args.dry_run:
            print(f"# {(ad['title'] or '')[:70]} (short description)\n   BEFORE: {ad['seller_notes'][:160]!r}\n   AFTER : {new!r}")
        else:
            sb.table("ad_analysis").update({"seller_notes": new}).eq("ad_url", ad["ad_url"]).execute()
        if new is None:
            cleared += 1
        else:
            kept += 1
    log.info("%s %d re-summarised, %d short ones recased, %d cleared.",
             "Would have:" if args.dry_run else "Done:", done, kept, cleared)


if __name__ == "__main__":
    main()
