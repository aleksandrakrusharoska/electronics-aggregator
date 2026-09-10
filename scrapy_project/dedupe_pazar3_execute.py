"""Executes the pazar3 duplicate cleanup described by dedupe_pazar3_dry_run.py.

For each "confident" duplicate group (same trailing numeric ID, title
similarity >= 0.5): keeps the row with the latest created_at (freshest
title/price/description — these ID-URL changes are real pazar3.mk 301
redirects, consistent with the seller editing/bumping the ad, so the
newest snapshot is the current one, not the oldest). Merges into it any
of listing_type/condition/category/description/seller_name that only an
older row has, then deletes the older row(s).

Groups below the similarity threshold (possible pazar3.mk ID reuse by
dealer/business accounts reposting different items into the same slot —
confirmed several real examples) are left completely untouched — no
merge, no delete.

Run this yourself after reviewing the dry-run output. It asks for
confirmation before deleting anything.
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
MERGE_FIELDS = ("listing_type", "condition", "category", "description", "seller_name")


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

    confident = []
    for gid, group in dupe_groups.items():
        group_sorted = sorted(group, key=lambda r: r["created_at"], reverse=True)
        keeper, dupes = group_sorted[0], group_sorted[1:]
        min_sim = min(title_similarity(keeper["title"], d["title"]) for d in dupes)
        if min_sim >= TITLE_SIMILARITY_THRESHOLD:
            confident.append({"id": gid, "keeper": keeper, "dupes": dupes})

    total_deletes = sum(len(e["dupes"]) for e in confident)
    print(f"Confident groups: {len(confident)}")
    print(f"Rows that would be deleted: {total_deletes}")
    print(f"Rows left untouched (below similarity threshold, possible ID reuse): "
          f"{len(dupe_groups) - len(confident)} groups")

    answer = input(f"\nProceed with merging + deleting {total_deletes} duplicate rows? [y/N] ").strip().lower()
    if answer != "y":
        print("Aborted — no changes made.")
        return

    merged, deleted, errors = 0, 0, 0
    for entry in confident:
        keeper, dupes = entry["keeper"], entry["dupes"]
        update = {}
        for d in dupes:
            for f in MERGE_FIELDS:
                if not keeper.get(f) and d.get(f):
                    update[f] = d[f]
        if update:
            try:
                sb.table("ads").update(update).eq("ad_url", keeper["ad_url"]).execute()
                merged += 1
            except Exception as exc:
                print(f"  Merge failed for {keeper['ad_url']}: {exc}")
                errors += 1
                continue
        for d in dupes:
            try:
                sb.table("ads").delete().eq("ad_url", d["ad_url"]).execute()
                deleted += 1
            except Exception as exc:
                print(f"  Delete failed for {d['ad_url']}: {exc}")
                errors += 1

    print(f"\nDone. Merged fields into {merged} keeper rows, deleted {deleted} duplicate rows, {errors} errors.")


if __name__ == "__main__":
    main()
