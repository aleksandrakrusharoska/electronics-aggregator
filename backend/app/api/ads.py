"""Ads API — serves data from Supabase."""
import logging
import time
from datetime import date, timedelta

from fastapi import APIRouter, Query
from app.core.cache import snapshot
from app.core.supabase import get_supabase

router = APIRouter(tags=["ads"])   # mounted in main.py
log = logging.getLogger(__name__)

PAGE_SIZE = 16  # 4 rows of 4 cards in the grid view
MAX_RETRIES = 3
MKD_PER_EUR = 61.5  # same fixed rate as the generated ads.price_mkd column

# The total for a filter combination changes only when the daily pipeline
# runs, so paging through results (or coming back to the list) reuses it
# for a few minutes instead of re-counting every matching ad each time.
COUNT_TTL_SECONDS = 300
_count_cache: dict[tuple, tuple[int, float]] = {}


def _execute_with_retry(query):
    """This table sees frequent transient statement timeouts under
    concurrent load from scheduled scraping/parsing jobs — retry a few
    times with backoff before giving up."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return query.execute()
        except Exception as exc:
            if attempt == MAX_RETRIES:
                raise
            wait = 2 ** attempt
            log.warning("Supabase query failed (attempt %d/%d): %s — retrying in %ds",
                        attempt, MAX_RETRIES, exc, wait)
            time.sleep(wait)

# Filters arrive as names ("pazar3", a category label) but are applied as
# IDs: filtering ads_view on a joined name column makes the planner badly
# underestimate the row count and pick a ~50x slower plan (measured: 1.1 s
# vs 21 ms for the default listing). The lookup tables are tiny, so they
# are cached per process; a name not in the cache triggers one reload.
_lookup_cache: dict[str, dict] = {}


def _lookup(table: str, id_col: str, key_fn) -> dict:
    if table not in _lookup_cache:
        rows = _execute_with_retry(get_supabase().table(table).select("*").limit(10000)).data
        index: dict = {}
        for r in rows:
            index.setdefault(key_fn(r), []).append(r[id_col])
        _lookup_cache[table] = index
    return _lookup_cache[table]


def _ids(table: str, id_col: str, key_fn, key) -> list[int]:
    ids = _lookup(table, id_col, key_fn).get(key)
    if ids is None:
        _lookup_cache.pop(table, None)
        ids = _lookup(table, id_col, key_fn).get(key)
    return ids or [-1]  # unknown name: match nothing instead of everything


def source_id_for(name: str) -> int:
    return _ids("sources", "source_id", lambda r: r["name"], name)[0]


def category_ids_for(name: str) -> list[int]:
    # the same label can exist on both portals
    return _ids("categories", "category_id", lambda r: r["name"], name)


AD_FIELDS = (
    "ad_url, title, price_eur, price_mkd, currency, location, "
    "images, category, condition, source, scraped_at, posted_date, "
    "seller_name, seller_type, specs, delivery_available, description, seller_notes, "
    "cluster_id, cluster_label, ad_type, is_active, "
    "brand, model, reference_new_price_mkd, reference_sample_size, reference_source, "
    "price_vs_new_ratio, good_price_deal, reference_stores, dup_group_id"
)


def _attach_other_listings(sb, items: list[dict]) -> list[dict]:
    """For ads in a duplicate group (the same seller's listing on both
    portals, or posted twice — see run_dedup_agent.update_groups), add
    `also_on`: the group's other active listings, cheapest first, so one
    card can link to all of them."""
    group_ids = sorted({a["dup_group_id"] for a in items if a.get("dup_group_id")})
    if not group_ids:
        return items
    others = _execute_with_retry(
        sb.table("ads_view")
        .select("ad_url, source, price_eur, dup_group_id")
        .in_("dup_group_id", group_ids)
        .or_("is_active.is.null,is_active.eq.true")
    ).data
    by_group: dict[int, list[dict]] = {}
    for o in others:
        by_group.setdefault(o["dup_group_id"], []).append(o)
    for a in items:
        group = by_group.get(a.get("dup_group_id"), [])
        a["also_on"] = sorted(
            ({"ad_url": o["ad_url"], "source": o["source"], "price_eur": o["price_eur"]}
             for o in group if o["ad_url"] != a["ad_url"]),
            key=lambda o: o["price_eur"] if o["price_eur"] is not None else float("inf"),
        )
    return items


@router.get("/suggest")
def suggest_ads(q: str = Query(..., min_length=1)):
    """Lightweight typeahead results for the search box — a handful of
    matching titles/thumbnails/prices, not full ad records."""
    sb = get_supabase()
    query = (
        sb.table("ads_view")
        .select("ad_url, title, price_eur, images")
        .or_("is_electronics.is.null,is_electronics.eq.true")
        .not_.is_("title", "null")
        .ilike("title", f"%{q}%")
        .order("posted_date", desc=True, nullsfirst=False)
        .limit(8)
    )
    rows = _execute_with_retry(query).data
    return [
        {
            "ad_url": r["ad_url"],
            "title": r["title"],
            "price_eur": r.get("price_eur"),
            "image": (r.get("images") or [None])[0],
        }
        for r in rows
    ]


@router.get("")
def list_ads(
    source: str | None = None,
    category: str | None = None,
    condition: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    q: str | None = None,
    sort: str = "newest",
    good_deal_only: bool = False,
    ad_type: str | None = None,
    page: int = Query(1, ge=1),
):
    sb = get_supabase()
    offset = (page - 1) * PAGE_SIZE
    old_cutoff = (date.today() - timedelta(days=3 * 365)).isoformat()
    # "Biggest discount" only makes sense among good deals: across all ads the
    # top is junk (0.02 € for a console) and the sort over the whole view
    # exceeds the statement timeout, while among good deals it takes ~1 s.
    if sort == "best_deal":
        good_deal_only = True

    def filtered(query):
        # Exclude ads the parser has confirmed aren't actually electronics (e.g.
        # toys/sporting goods mis-filed under an electronics category on the
        # source site). Not-yet-classified ads (is_electronics IS NULL) still
        # show — only explicit False gets hidden.
        query = query.or_("is_electronics.is.null,is_electronics.eq.true")
        # Same pattern for listings the rescrape spiders confirmed via a 404 are
        # no longer live — is_active IS NULL means "never re-checked", which
        # still shows (most ads), only a confirmed-gone False gets hidden.
        query = query.or_("is_active.is.null,is_active.eq.true")
        # Ads confirmed older than 3 years are the pazar3 historical-archive
        # backfill — kept in the DB for possible future use, but not shown as
        # current listings for now. Unknown-age (no posted_date yet) still shows.
        query = query.or_(f"posted_date.gte.{old_cutoff},posted_date.is.null")
        # One card per duplicate group: the other listings of the same
        # seller's ad are linked from it (also_on), not listed again. With a
        # source filter every listing of that source shows, since the
        # group's main ad may be on the other portal.
        if not source:
            query = query.or_("dup_primary.is.null,dup_primary.eq.true")

        if source:
            query = query.eq("source_id", source_id_for(source))
        if category:
            query = query.in_("category_id", category_ids_for(category))
        if condition:
            query = query.eq("condition", condition)
        # price filters/sort go through the real, indexed price_mkd column —
        # price_eur is computed in the view, so it can't use an index
        if min_price is not None:
            query = query.gte("price_mkd", min_price * MKD_PER_EUR)
        if max_price is not None:
            query = query.lte("price_mkd", max_price * MKD_PER_EUR)
        if q:
            query = query.ilike("title", f"%{q}%")
        if good_deal_only:
            query = query.eq("good_price_deal", True)
        if ad_type:
            query = query.eq("ad_type", ad_type)
        return query

    query = filtered(sb.table("ads_view").select(AD_FIELDS))
    if sort == "price_asc":
        query = query.order("price_mkd", desc=False, nullsfirst=False)
    elif sort == "price_desc":
        query = query.order("price_mkd", desc=True, nullsfirst=False)
    elif sort == "best_deal":
        # lowest price relative to the reference price first
        query = query.order("price_vs_new_ratio", desc=False, nullsfirst=False).order("ad_url")
    else:
        # posted_date is a date (no time component), so ties are common —
        # break them with scraped_at for stable pagination. nullsfirst=False
        # keeps ads with an unresolved posted_date (not yet backfilled) from
        # sorting to the top.
        query = query.order("posted_date", desc=True, nullsfirst=False).order("scraped_at", desc=True)
    result = _execute_with_retry(query.range(offset, offset + PAGE_SIZE - 1))

    # The total is a separate, count-only request: asking for count="exact"
    # on the page query makes PostgREST materialize every matching row with
    # all its fields (descriptions included) just to count them, which
    # exceeded the statement timeout through the joined view. Measured on
    # the test project: page alone 0.6 s, count alone 0.3 s, both in one
    # request > 3 s (timeout).
    count_key = (source, category, condition, min_price, max_price, q, good_deal_only, ad_type)
    cached_total = _count_cache.get(count_key)
    if cached_total and time.monotonic() - cached_total[1] < COUNT_TTL_SECONDS:
        total = cached_total[0]
    else:
        try:
            try:
                total = filtered(sb.table("ads_view").select("ad_url", count="exact", head=True)).execute().count or 0
            except Exception:
                # measured 0.4-3.6 s for the same query, so a second try usually makes it
                total = filtered(sb.table("ads_view").select("ad_url", count="exact", head=True)).execute().count or 0
            _count_cache[count_key] = (total, time.monotonic())
        except Exception as exc:
            # The exact count over the joined view takes 0.4-3.6 s and the
            # statement timeout is 3 s, so it sometimes fails — and used to
            # take the whole page down with it. Fall back to the last exact
            # total for these filters, else Postgres's planner estimate
            # (instant; only the page count is approximate). Not cached, so
            # the next request tries the exact count again.
            log.warning("Exact count failed, using an estimate: %s", exc)
            if cached_total:
                total = cached_total[0]
            else:
                total = _execute_with_retry(
                    filtered(sb.table("ads_view").select("ad_url", count="planned", head=True))).count or 0

    return {
        "items": _attach_other_listings(sb, result.data),
        "total": total,
        "page": page,
        "pages": max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE),
    }


@router.get("/detail")
def get_ad_detail(ad_url: str):
    """Fetch a single ad by its ad_url — used to restore a deep-linked ad
    (opened via a shared URL) that may not be present in the caller's
    current filtered/paginated result set."""
    sb = get_supabase()
    result = _execute_with_retry(
        sb.table("ads_view").select(AD_FIELDS).eq("ad_url", ad_url).limit(1)
    )
    return _attach_other_listings(sb, result.data)[0] if result.data else None


@router.get("/batch")
def get_ads_batch(ad_urls: str):
    """Fetch multiple ads by ad_url (comma-separated) in one call — used by
    the wishlist panel to show live data instead of the frozen snapshot it
    used to store in localStorage at save-time."""
    urls = [u for u in ad_urls.split(",") if u]
    if not urls:
        return []
    sb = get_supabase()
    result = _execute_with_retry(sb.table("ads_view").select(AD_FIELDS).in_("ad_url", urls))
    return _attach_other_listings(sb, result.data)


@router.get("/stats")
def get_stats():
    # One SQL function (ad_stats, see sql/migrations/001) instead of eight
    # separate count queries, which intermittently hit the statement timeout.
    # Uses the same electronics filter as list_ads, so the sidebar counts
    # equal what clicking through returns.
    return _execute_with_retry(get_supabase().rpc("ad_stats")).data


@router.get("/similar")
def get_similar(cluster_id: int, exclude_url: str | None = None, limit: int = 6):
    sb = get_supabase()
    q = (
        sb.table("ads_view")
        .select(AD_FIELDS)
        .eq("cluster_id", cluster_id)
        .eq("ad_type", "product")
        .not_.is_("images", "null")
    )
    if exclude_url:
        q = q.neq("ad_url", exclude_url)
    result = _execute_with_retry(q.order("scraped_at", desc=True).limit(limit))
    return result.data


@router.get("/analytics/brands")
@snapshot("brands")
def get_brand_analytics(source: str | None = None):
    import statistics
    from collections import Counter

    # Two-tier ground truth, mirroring reference_price_agent.py's own
    # design. Tier 1: trust an actual reference price (the median of other
    # New-condition marketplace listings of the same model, or its price in
    # Macedonian stores) when one exists, so only its own plausibility ratio
    # filters it. Tier 2: ads with no reference at all fall back to the
    # same domain floor used elsewhere (see memory
    # project_bogus_low_prices.md) — imperfect, but far better than none.
    # A pure floor for everyone (tried first) still let bogus-priced
    # laptops through since real laptop prices span such a wide range;
    # requiring a reference for everyone (tried second) gutted brands with
    # little reference coverage. This combines both.
    MIN_PLAUSIBLE_RATIO = 0.10        # mirrors reference_price_agent.py
    MIN_PLAUSIBLE_PRICE_EUR = 24.39   # mirrors MIN_PLAUSIBLE_PRICE_MKD (1500 MKD)

    sb = get_supabase()
    # Keyed by lowercased brand (the LLM-normalized `brand` field isn't
    # perfectly case-consistent — "Asus" vs "ASUS", "Dell" vs "DELL" — so
    # group case-insensitively and use the most common original casing as
    # the display label, rather than fragmenting into duplicate rows.
    brand_prices: dict[str, list[float]] = {}
    brand_labels: dict[str, Counter] = {}

    last_url, batch = None, 1000
    while True:
        q = (
            sb.table("ads_view")
            .select("ad_url, brand, price_eur, reference_new_price_mkd, price_vs_new_ratio")
            .eq("ad_type", "product")
            .not_.is_("brand", "null")
            .not_.is_("price_eur", "null")
            .gt("price_eur", 0)
            .order("ad_url")
        )
        if source:
            q = q.eq("source_id", source_id_for(source))
        if last_url is not None:
            q = q.gt("ad_url", last_url)
        rows = _execute_with_retry(q.limit(batch)).data
        if not rows:
            break
        for row in rows:
            brand = (row.get("brand") or "").strip()
            price = row.get("price_eur")
            if not brand or not price:
                continue
            if row.get("reference_new_price_mkd") is not None:
                ratio = row.get("price_vs_new_ratio")
                if ratio is None or ratio < MIN_PLAUSIBLE_RATIO:
                    continue
            elif float(price) < MIN_PLAUSIBLE_PRICE_EUR:
                continue
            key = brand.lower()
            brand_prices.setdefault(key, []).append(float(price))
            brand_labels.setdefault(key, Counter())[brand] += 1
        if len(rows) < batch:
            break
        last_url = rows[-1]["ad_url"]

    result = []
    for key, prices in brand_prices.items():
        if len(prices) < 3:
            continue
        sorted_p = sorted(prices)
        n = len(sorted_p)
        q1 = sorted_p[max(0, n // 4 - 1)]
        q3 = sorted_p[min(n - 1, 3 * n // 4)]
        iqr = q3 - q1
        low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        filtered = [p for p in sorted_p if low <= p <= high]
        if len(filtered) < 3:
            filtered = sorted_p
        fn = len(filtered)
        result.append({
            "brand": brand_labels[key].most_common(1)[0][0],
            "count": n,
            "avg_price": round(sum(filtered) / fn, 2),
            "min_price": round(filtered[0], 2),
            "max_price": round(filtered[-1], 2),
            "median_price": round(statistics.median(filtered), 2),
            "q1": round(q1, 2),
            "q3": round(q3, 2),
        })

    return sorted(result, key=lambda x: -x["count"])


@router.get("/analytics/good-deals")
@snapshot("good_deals")
def get_good_deal_analytics():
    """Per-brand share of listings flagged good_price_deal by the reference-
    price agent — surfaces which brands most often turn up under market
    price, rather than just raw price stats."""
    from collections import Counter

    MIN_SAMPLE = 10  # below this a percentage is just noise

    sb = get_supabase()
    brand_total: dict[str, int] = {}
    brand_good: dict[str, int] = {}
    brand_labels: dict[str, Counter] = {}

    last_url, batch = None, 1000
    while True:
        q = (
            sb.table("ads_view")
            .select("ad_url, brand, good_price_deal")
            .eq("ad_type", "product")
            .not_.is_("brand", "null")
            .order("ad_url")
        )
        if last_url is not None:
            q = q.gt("ad_url", last_url)
        rows = _execute_with_retry(q.limit(batch)).data
        if not rows:
            break
        for row in rows:
            brand = (row.get("brand") or "").strip()
            if not brand:
                continue
            key = brand.lower()
            brand_labels.setdefault(key, Counter())[brand] += 1
            brand_total[key] = brand_total.get(key, 0) + 1
            if row.get("good_price_deal"):
                brand_good[key] = brand_good.get(key, 0) + 1
        if len(rows) < batch:
            break
        last_url = rows[-1]["ad_url"]

    result = []
    for key, total in brand_total.items():
        if total < MIN_SAMPLE:
            continue
        good = brand_good.get(key, 0)
        result.append({
            "brand": brand_labels[key].most_common(1)[0][0],
            "count": total,
            "good_deal_count": good,
            "good_deal_pct": round(100 * good / total, 1),
        })

    return sorted(result, key=lambda x: -x["good_deal_pct"])


@router.get("/analytics/scrape-activity")
@snapshot("scrape_activity")
def get_scrape_activity():
    """Daily count of ads first scraped (by scraped_at, not posted_date),
    per source, over the last 14 days — pipeline health, not market
    activity: shows whether the scrapers are actively finding new listings
    day to day, unlike /analytics/trend which tracks when ads were posted."""
    from collections import defaultdict
    from datetime import date, timedelta

    cutoff = (date.today() - timedelta(days=13)).isoformat()

    sb = get_supabase()
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"pazar3": 0, "reklama5": 0})

    last_url, batch = None, 1000
    while True:
        q = (
            sb.table("ads_view")
            .select("ad_url, source, scraped_at")
            .gte("scraped_at", cutoff)
            .order("ad_url")
        )
        if last_url is not None:
            q = q.gt("ad_url", last_url)
        rows = _execute_with_retry(q.limit(batch)).data
        if not rows:
            break
        for row in rows:
            scraped = row.get("scraped_at")
            source = row.get("source")
            if not scraped or source not in ("pazar3", "reklama5"):
                continue
            day = scraped[:10]
            counts[day][source] += 1
        if len(rows) < batch:
            break
        last_url = rows[-1]["ad_url"]

    days = [(date.today() - timedelta(days=n)).isoformat() for n in range(13, -1, -1)]
    return [
        {"date": d, "pazar3": counts[d]["pazar3"], "reklama5": counts[d]["reklama5"]}
        for d in days
    ]


@router.get("/analytics/trend")
@snapshot("trend")
def get_listing_trend():
    """Monthly listing volume per source over the last 12 months — shows
    whether activity on each platform is growing or shrinking."""
    from collections import defaultdict
    from datetime import date

    today = date.today()
    total_months = today.year * 12 + (today.month - 1) - 11
    cutoff_year, cutoff_month0 = divmod(total_months, 12)
    cutoff = date(cutoff_year, cutoff_month0 + 1, 1).isoformat()

    sb = get_supabase()
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"pazar3": 0, "reklama5": 0})

    last_url, batch = None, 1000
    while True:
        q = (
            sb.table("ads_view")
            .select("ad_url, source, posted_date")
            .eq("ad_type", "product")
            .gte("posted_date", cutoff)
            .order("ad_url")
        )
        if last_url is not None:
            q = q.gt("ad_url", last_url)
        rows = _execute_with_retry(q.limit(batch)).data
        if not rows:
            break
        for row in rows:
            posted = row.get("posted_date")
            source = row.get("source")
            if not posted or source not in ("pazar3", "reklama5"):
                continue
            month = posted[:7]
            counts[month][source] += 1
        if len(rows) < batch:
            break
        last_url = rows[-1]["ad_url"]

    return [
        {"month": month, "pazar3": c["pazar3"], "reklama5": c["reklama5"]}
        for month, c in sorted(counts.items())
    ]


@router.get("/analytics/depreciation")
@snapshot("depreciation")
def get_depreciation_analytics():
    import statistics

    # Canonical condition categories, ordered New -> most-used, matching the
    # scale the LLM parser normalizes every ad's condition into.
    CONDITION_ORDER = ["New", "Used - Like New", "Used - Good", "Used - Fair", "Used", "For parts"]

    # Hard floor, not just IQR trimming: a meaningful slice of listings
    # (shop ads, mostly) show a monthly installment price ("на рати") as the
    # ad's headline price instead of the full price — e.g. an iPhone 17 Pro
    # Max at 559 MKD/month reads as ~0.6% of its reference new price. IQR
    # alone can't handle this since these aren't rare outliers: they're a
    # large enough share of some condition buckets (~40% of "New") to drag
    # the IQR bounds themselves down with them. Nothing legitimately sells
    # for under a tenth of the reference new price, so filter at the query
    # level before any stats are computed.
    sb = get_supabase()
    by_condition: dict[str, list[float]] = {c: [] for c in CONDITION_ORDER}

    last_url, batch = None, 1000
    while True:
        q = (
            sb.table("ads_view")
            .select("ad_url, condition, price_vs_new_ratio")
            .not_.is_("price_vs_new_ratio", "null")
            .gte("price_vs_new_ratio", 0.1)
            .in_("condition", CONDITION_ORDER)
            .order("ad_url")
        )
        if last_url is not None:
            q = q.gt("ad_url", last_url)
        rows = _execute_with_retry(q.limit(batch)).data
        if not rows:
            break
        for row in rows:
            cond = row.get("condition")
            ratio = row.get("price_vs_new_ratio")
            if ratio is not None:
                by_condition[cond].append(float(ratio) * 100)
        if len(rows) < batch:
            break
        last_url = rows[-1]["ad_url"]

    result = []
    for cond in CONDITION_ORDER:
        pcts = by_condition[cond]
        if len(pcts) < 3:
            continue
        sorted_p = sorted(pcts)
        n = len(sorted_p)
        # Same IQR-based outlier trim as /analytics/brands — a handful of
        # mispriced or bundled listings shouldn't skew the average shown.
        q1 = sorted_p[max(0, n // 4 - 1)]
        q3 = sorted_p[min(n - 1, 3 * n // 4)]
        iqr = q3 - q1
        low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        filtered = [p for p in sorted_p if low <= p <= high]
        if len(filtered) < 3:
            filtered = sorted_p
        result.append({
            "condition": cond,
            "count": n,
            "avg_pct_of_new": round(sum(filtered) / len(filtered), 1),
            "median_pct_of_new": round(statistics.median(filtered), 1),
        })

    return result


@router.get("/categories")
def get_categories():
    # Counted in the database (category_counts, see sql/migrations/001)
    # instead of paging through every ad on each page load.
    return _execute_with_retry(get_supabase().rpc("category_counts")).data
