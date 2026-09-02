"""Ads API — serves data from Supabase."""
import logging
import time
from datetime import date, timedelta

from fastapi import APIRouter, Query
from app.core.supabase import get_supabase

router = APIRouter(prefix="/api/ads", tags=["ads"])
log = logging.getLogger(__name__)

PAGE_SIZE = 20
MAX_RETRIES = 3


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

AD_FIELDS = (
    "ad_url, title, price_eur, price_mkd, currency, location, "
    "images, category, condition, source, scraped_at, posted_date, "
    "seller_name, seller_type, specs, delivery_available, description, seller_notes, "
    "cluster_id, cluster_label, ad_type, is_active, "
    "brand, model, reference_new_price_mkd, reference_sample_size, reference_source, "
    "price_vs_new_ratio, good_price_deal"
)


@router.get("/suggest")
def suggest_ads(q: str = Query(..., min_length=1)):
    """Lightweight typeahead results for the search box — a handful of
    matching titles/thumbnails/prices, not full ad records."""
    sb = get_supabase()
    query = (
        sb.table("ads")
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

    query = sb.table("ads").select(AD_FIELDS, count="exact")
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
    old_cutoff = (date.today() - timedelta(days=3 * 365)).isoformat()
    query = query.or_(f"posted_date.gte.{old_cutoff},posted_date.is.null")

    if source:
        query = query.eq("source", source)
    if category:
        query = query.eq("category", category)
    if condition:
        query = query.eq("condition", condition)
    if min_price is not None:
        query = query.gte("price_eur", min_price)
    if max_price is not None:
        query = query.lte("price_eur", max_price)
    if q:
        query = query.ilike("title", f"%{q}%")
    if good_deal_only:
        query = query.eq("good_price_deal", True)
    if ad_type:
        query = query.eq("ad_type", ad_type)

    if sort == "price_asc":
        query = query.order("price_eur", desc=False, nullsfirst=False)
    elif sort == "price_desc":
        query = query.order("price_eur", desc=True, nullsfirst=False)
    else:
        # posted_date is a date (no time component), so ties are common —
        # break them with scraped_at for stable pagination. nullsfirst=False
        # keeps ads with an unresolved posted_date (not yet backfilled) from
        # sorting to the top.
        query = query.order("posted_date", desc=True, nullsfirst=False).order("scraped_at", desc=True)

    result = _execute_with_retry(query.range(offset, offset + PAGE_SIZE - 1))

    return {
        "items": result.data,
        "total": result.count or 0,
        "page": page,
        "pages": max(1, ((result.count or 0) + PAGE_SIZE - 1) // PAGE_SIZE),
    }


@router.get("/detail")
def get_ad_detail(ad_url: str):
    """Fetch a single ad by its ad_url — used to restore a deep-linked ad
    (opened via a shared URL) that may not be present in the caller's
    current filtered/paginated result set."""
    sb = get_supabase()
    result = _execute_with_retry(
        sb.table("ads").select(AD_FIELDS).eq("ad_url", ad_url).limit(1)
    )
    return result.data[0] if result.data else None


@router.get("/batch")
def get_ads_batch(ad_urls: str):
    """Fetch multiple ads by ad_url (comma-separated) in one call — used by
    the wishlist panel to show live data instead of the frozen snapshot it
    used to store in localStorage at save-time."""
    urls = [u for u in ad_urls.split(",") if u]
    if not urls:
        return []
    sb = get_supabase()
    result = _execute_with_retry(sb.table("ads").select(AD_FIELDS).in_("ad_url", urls))
    return result.data


@router.get("/stats")
def get_stats():
    sb = get_supabase()
    # Match list_ads' own filter exactly, so these sidebar counts equal what
    # clicking through actually returns — ads explicitly flagged not-real-
    # electronics (is_electronics = False) are excluded there, so they must
    # be excluded here too.
    ELECTRONICS_FILTER = "is_electronics.is.null,is_electronics.eq.true"

    total = _execute_with_retry(sb.table("ads").select("ad_url", count="exact").or_(ELECTRONICS_FILTER)).count or 0
    r5 = _execute_with_retry(sb.table("ads").select("ad_url", count="exact").or_(ELECTRONICS_FILTER).eq("source", "reklama5")).count or 0
    p3 = _execute_with_retry(sb.table("ads").select("ad_url", count="exact").or_(ELECTRONICS_FILTER).eq("source", "pazar3")).count or 0
    dupes = _execute_with_retry(sb.table("duplicates").select("id", count="exact")).count or 0
    good_deals = _execute_with_retry(sb.table("ads").select("ad_url", count="exact").eq("good_price_deal", True)).count or 0
    products = _execute_with_retry(sb.table("ads").select("ad_url", count="exact").or_(ELECTRONICS_FILTER).eq("ad_type", "product")).count or 0
    services = _execute_with_retry(sb.table("ads").select("ad_url", count="exact").or_(ELECTRONICS_FILTER).eq("ad_type", "service")).count or 0
    wanted = _execute_with_retry(sb.table("ads").select("ad_url", count="exact").or_(ELECTRONICS_FILTER).eq("ad_type", "wanted")).count or 0

    return {
        "total": total,
        "sources": {"reklama5": r5, "pazar3": p3},
        "duplicates": dupes,
        "good_deals": good_deals,
        "ad_types": {"product": products, "service": services, "wanted": wanted},
    }


@router.get("/similar")
def get_similar(cluster_id: int, exclude_url: str | None = None, limit: int = 6):
    sb = get_supabase()
    q = (
        sb.table("ads")
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
def get_brand_analytics(source: str | None = None):
    import statistics
    from collections import Counter

    # Two-tier ground truth, mirroring reference_price_agent.py's own
    # design. Tier 1: trust an actual reference-price match (Setec's live
    # catalog, or the median of other New-condition marketplace listings
    # of the same model) when one exists — a real cross-check, not a
    # guess, so only its own plausibility ratio filters it. Tier 2: most
    # ads never get a reference match at all (Setec only stocks current
    # phones — no laptops — and marketplace fallback needs 2+ New-condition
    # listings of the exact same model, which laptops rarely have), so
    # fall back to the same domain floor used elsewhere (see memory
    # project_bogus_low_prices.md) — imperfect, but far better than none.
    # A pure floor for everyone (tried first) still let bogus-priced
    # laptops through since real laptop prices span such a wide range;
    # requiring a reference match for everyone (tried second) guts laptop
    # brands entirely since Setec doesn't carry them. This combines both.
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
            sb.table("ads")
            .select("ad_url, brand, price_eur, reference_new_price_mkd, price_vs_new_ratio")
            .eq("ad_type", "product")
            .not_.is_("brand", "null")
            .not_.is_("price_eur", "null")
            .gt("price_eur", 0)
            .order("ad_url")
        )
        if source:
            q = q.eq("source", source)
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
            sb.table("ads")
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
            sb.table("ads")
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
            sb.table("ads")
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
            sb.table("ads")
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
    sb = get_supabase()
    # Fetch in pages and count server-side
    cats: dict[str, int] = {}
    last_url = None
    batch = 1000
    while True:
        q = (
            sb.table("ads")
            .select("ad_url, category")
            .not_.is_("category", "null")
            .neq("category", "")
            .order("ad_url")
        )
        if last_url is not None:
            q = q.gt("ad_url", last_url)
        rows = _execute_with_retry(q.limit(batch)).data
        if not rows:
            break
        for row in rows:
            c = row.get("category") or ""
            if c:
                cats[c] = cats.get(c, 0) + 1
        if len(rows) < batch:
            break
        last_url = rows[-1]["ad_url"]

    return sorted(
        [{"name": k, "count": v} for k, v in cats.items()],
        key=lambda x: -x["count"],
    )[:40]
