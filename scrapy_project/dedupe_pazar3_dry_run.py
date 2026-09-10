"""Dry-run report for pazar3 ad_url duplicates caused by the redirect bug
(fixed in pazar3_rescrape_spider.py / pazar3_spider.py — response.url was
used instead of the originally-discovered URL, so every "fixed" ad
silently inserted a new row under pazar3.mk's canonical redirected URL).

Groups rows by the trailing numeric ID in ad_url (pazar3's own listing
ID). For each group with 2+ rows, picks the LATEST created_at as the
"keeper" — confirmed the URL changes come from real pazar3.mk 301
redirects (old slug -> new slug, both still resolving), consistent with
a seller editing/bumping the ad and the site regenerating its slug, so
the newest row has the current title/price/description, not stale
pre-edit values. Reports what would be merged into it (any field only an
older row has) and what would be deleted — makes NO changes. Flags
groups whose titles look too different to be confidently the same
listing (possible ID reuse by pazar3.mk), so those can be reviewed by
hand instead of auto-merged.
"""
import os
import re
from collections import defaultdict
from difflib import SequenceMatcher

from dotenv import load_dotenv

load_dotenv()
from supabase import create_client

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

FIELDS = "ad_url,title,price_mkd,created_at,listing_type,condition,category,description,seller_name,is_active"
TITLE_SIMILARITY_THRESHOLD = 0.5


def fetch_all():
    rows = []
    last_url = None
    while True:
        q = sb.table("ads").select(FIELDS).eq("source", "pazar3").order("ad_url").limit(1000)
        if last_url:
            q = q.gt("ad_url", last_url)
        batch = q.execute().data
        if not batch:
            break
        rows.extend(batch)
        last_url = batch[-1]["ad_url"]
        if len(batch) < 1000:
            break
    return rows


def title_similarity(a, b):
    a = (a or "").lower()
    b = (b or "").lower()
    return SequenceMatcher(None, a, b).ratio()


def main():
    rows = fetch_all()
    print(f"Scanned {len(rows)} pazar3 rows")

    groups = defaultdict(list)
    for r in rows:
        m = re.search(r"(\d+)$", r["ad_url"])
        if m:
            groups[m.group(1)].append(r)

    dupe_groups = {k: v for k, v in groups.items() if len(v) > 1}
    print(f"Duplicate groups: {len(dupe_groups)}")
    print(f"Excess rows (would be deleted if all confirmed): {sum(len(v) - 1 for v in dupe_groups.values())}")

    confident, review = [], []
    for gid, group in dupe_groups.items():
        # Newest first: group_sorted[0] is the keeper (current data),
        # everything after it is an older snapshot to merge-from then delete.
        group_sorted = sorted(group, key=lambda r: r["created_at"], reverse=True)
        keeper, dupes = group_sorted[0], group_sorted[1:]
        min_sim = min(title_similarity(keeper["title"], d["title"]) for d in dupes)
        entry = {"id": gid, "keeper": keeper, "dupes": dupes, "min_title_similarity": min_sim}
        if min_sim >= TITLE_SIMILARITY_THRESHOLD:
            confident.append(entry)
        else:
            review.append(entry)

    print(f"\nConfident matches (title similarity >= {TITLE_SIMILARITY_THRESHOLD}): {len(confident)} groups")
    print(f"Needs manual review (titles look too different — possible ID reuse): {len(review)} groups")

    if review:
        print("\n--- Sample of groups needing review ---")
        for entry in review[:10]:
            print(f"ID {entry['id']} (min title similarity {entry['min_title_similarity']:.2f}):")
            for r in [entry["keeper"]] + entry["dupes"]:
                print(f"    {r['created_at']}  {r['title']!r}  {r['ad_url']}")

    # What fields would actually get merged into keepers (confident group only)
    fields_gained = defaultdict(int)
    for entry in confident:
        keeper = entry["keeper"]
        for d in entry["dupes"]:
            for f in ("listing_type", "condition", "category", "description", "seller_name"):
                if not keeper.get(f) and d.get(f):
                    fields_gained[f] += 1

    print("\n--- Fields that would be gained by the keeper row (confident groups) ---")
    for f, n in fields_gained.items():
        print(f"  {f}: {n} rows would gain this field from a duplicate")

    print(f"\nNo changes made. This was a dry run.")


if __name__ == "__main__":
    main()
