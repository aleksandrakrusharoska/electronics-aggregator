"""Ads API — serves data from Supabase."""
from fastapi import APIRouter, Query
from app.core.supabase import get_supabase

router = APIRouter(prefix="/api/ads", tags=["ads"])

PAGE_SIZE = 24

AD_FIELDS = (
    "ad_url, title, price_eur, price_mkd, currency, location, "
    "images, category, condition, source, scraped_at, posted_date, "
    "seller_name, seller_type, specs, delivery_available, description, seller_notes, "
    "cluster_id, cluster_label, ad_type, "
    "brand, model, reference_new_price_mkd, reference_sample_size, reference_source, "
    "price_vs_new_ratio, good_price_deal"
)


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

    result = query.range(offset, offset + PAGE_SIZE - 1).execute()

    return {
        "items": result.data,
        "total": result.count or 0,
        "page": page,
        "pages": max(1, ((result.count or 0) + PAGE_SIZE - 1) // PAGE_SIZE),
    }


@router.get("/stats")
def get_stats():
    sb = get_supabase()
    total = sb.table("ads").select("ad_url", count="exact").execute().count or 0
    r5 = sb.table("ads").select("ad_url", count="exact").eq("source", "reklama5").execute().count or 0
    p3 = sb.table("ads").select("ad_url", count="exact").eq("source", "pazar3").execute().count or 0
    dupes = sb.table("duplicates").select("id", count="exact").execute().count or 0
    good_deals = sb.table("ads").select("ad_url", count="exact").eq("good_price_deal", True).execute().count or 0
    services = sb.table("ads").select("ad_url", count="exact").eq("ad_type", "service").execute().count or 0
    wanted = sb.table("ads").select("ad_url", count="exact").eq("ad_type", "wanted").execute().count or 0

    return {
        "total": total,
        "sources": {"reklama5": r5, "pazar3": p3},
        "duplicates": dupes,
        "good_deals": good_deals,
        "ad_types": {"service": services, "wanted": wanted},
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
    result = q.order("scraped_at", desc=True).limit(limit).execute()
    return result.data


@router.get("/analytics/brands")
def get_brand_analytics():
    import re
    import statistics

    BRANDS = {
        'Apple':    ['iphone', 'ipad', 'macbook', 'imac', 'airpod'],
        'Samsung':  ['samsung', 'galaxy'],
        'Xiaomi':   ['xiaomi', 'redmi', 'poco'],
        'Huawei':   ['huawei'],
        'Honor':    ['honor'],
        'Sony':     ['sony', 'xperia'],
        'Lenovo':   ['lenovo', 'thinkpad', 'ideapad'],
        'Dell':     ['dell'],
        'Asus':     ['asus', 'rog'],
        'Acer':     ['acer'],
        'Motorola': ['motorola', 'moto g', 'moto e'],
        'OnePlus':  ['oneplus', 'one plus'],
        'Nokia':    ['nokia'],
        'Realme':   ['realme'],
        'Google':   ['pixel'],
    }
    HP_RE = re.compile(r'\bhp\b')

    sb = get_supabase()
    brand_prices: dict[str, list[float]] = {b: [] for b in BRANDS}
    brand_prices['HP'] = []

    offset, batch = 0, 1000
    while True:
        rows = (
            sb.table("ads")
            .select("title, price_eur")
            .eq("ad_type", "product")
            .not_.is_("price_eur", "null")
            .gt("price_eur", 0)
            .range(offset, offset + batch - 1)
            .execute()
            .data
        )
        if not rows:
            break
        for row in rows:
            title = (row.get("title") or "").lower()
            price = row.get("price_eur")
            if not price:
                continue
            matched = False
            for brand, keywords in BRANDS.items():
                if any(kw in title for kw in keywords):
                    brand_prices[brand].append(float(price))
                    matched = True
                    break
            if not matched and HP_RE.search(title):
                brand_prices['HP'].append(float(price))
        if len(rows) < batch:
            break
        offset += batch
        if offset >= 60000:
            break

    result = []
    for brand, prices in brand_prices.items():
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
            "brand": brand,
            "count": n,
            "avg_price": round(sum(filtered) / fn, 2),
            "min_price": round(filtered[0], 2),
            "max_price": round(filtered[-1], 2),
            "median_price": round(statistics.median(filtered), 2),
            "q1": round(q1, 2),
            "q3": round(q3, 2),
        })

    return sorted(result, key=lambda x: -x["count"])


@router.get("/categories")
def get_categories():
    sb = get_supabase()
    # Fetch in pages and count server-side
    cats: dict[str, int] = {}
    offset = 0
    batch = 1000
    while True:
        rows = (
            sb.table("ads")
            .select("category")
            .not_.is_("category", "null")
            .neq("category", "")
            .range(offset, offset + batch - 1)
            .execute()
            .data
        )
        if not rows:
            break
        for row in rows:
            c = row.get("category") or ""
            if c:
                cats[c] = cats.get(c, 0) + 1
        if len(rows) < batch:
            break
        offset += batch

    return sorted(
        [{"name": k, "count": v} for k, v in cats.items()],
        key=lambda x: -x["count"],
    )[:40]
