"""
Orchestrator agent — coordinates the full ad aggregation pipeline.

Uses LangChain tool-calling with ChatGroq (LLM) to reason about the current
state of the database and decide which agents to run and in what order.

Each processing step is exposed as a LangChain @tool. The LLM reads the
pipeline status and calls the appropriate tools sequentially.

Individual agents can still be run manually at any time:
    python run_classification_agent.py
    python run_parser_agent.py --limit 500
    python run_dedup_agent.py
    python run_clustering_agent.py
"""
import logging
import os
import time

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from supabase import create_client

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


def _sb():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ── Tools (each wraps one agent) ──────────────────────────────────────────────

@tool
def check_pipeline_status() -> str:
    """
    Check the current state of the pipeline by querying the database.
    Returns counts of total ads, how many are classified, parsed (have specs),
    how many duplicate pairs exist, and how many have cluster assignments.
    Call this first before deciding what to run.
    """
    sb = _sb()
    total      = sb.table("ads").select("ad_url", count="exact").execute().count or 0
    classified = sb.table("ads").select("ad_url", count="exact").not_.is_("ad_type", "null").execute().count or 0
    parsed     = sb.table("ads").select("ad_url", count="exact").not_.is_("specs", "null").execute().count or 0
    duplicates = sb.table("duplicates").select("id", count="exact").execute().count or 0
    clustered  = sb.table("ads").select("ad_url", count="exact").not_.is_("cluster_id", "null").execute().count or 0
    products   = sb.table("ads").select("ad_url", count="exact").eq("ad_type", "product").execute().count or 0
    services   = sb.table("ads").select("ad_url", count="exact").eq("ad_type", "service").execute().count or 0
    wanted     = sb.table("ads").select("ad_url", count="exact").eq("ad_type", "wanted").execute().count or 0

    return (
        f"Pipeline status:\n"
        f"  Total ads:       {total:,}\n"
        f"  Classified:      {classified:,} ({100*classified//total if total else 0}%) "
        f"[product={products:,}, service={services:,}, wanted={wanted:,}]\n"
        f"  LLM-parsed:      {parsed:,} ({100*parsed//total if total else 0}%)\n"
        f"  Duplicate pairs: {duplicates:,}\n"
        f"  Clustered:       {clustered:,} ({100*clustered//total if total else 0}%)\n"
    )


@tool
def run_classification(dummy: str = "") -> str:
    """
    Run the classification agent to label every ad as 'product', 'service', or 'wanted'.
    This should run before dedup and clustering so those agents work on clean product data.
    Fast — no LLM, uses keyword matching.
    """
    from agents.classification_agent import classify_ads

    sb = _sb()
    ads, offset = [], 0
    while True:
        batch = sb.table("ads").select("ad_url, title, description, source") \
            .order("ad_url").range(offset, offset + 999).execute().data
        if not batch:
            break
        ads.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000

    results = classify_ads(ads)

    for i in range(0, len(results), 500):
        sb.table("ads").upsert(results[i:i+500], on_conflict="ad_url").execute()

    counts = {}
    for r in results:
        counts[r["ad_type"]] = counts.get(r["ad_type"], 0) + 1

    return (
        f"Classification complete: {len(results):,} ads labelled — "
        f"product={counts.get('product',0):,}, "
        f"service={counts.get('service',0):,}, "
        f"wanted={counts.get('wanted',0):,}"
    )


@tool
def run_parser(limit: int = 200) -> str:
    """
    Run the LLM parser agent using LangChain + Groq to extract structured specs
    (RAM, storage, display, battery, etc.) from ad descriptions.
    Processes up to `limit` ads that have not been parsed yet.
    Respects Groq rate limits automatically (4 second delay between requests).
    """
    from agents.parser_agent import build_parser, parse_ad

    sb = _sb()
    rows = (
        sb.table("ads")
        .select("ad_url, title, description")
        .is_("llm_parsed_at", "null")
        .not_.is_("description", "null")
        .limit(limit)
        .execute()
        .data
    )

    if not rows:
        return "No unparsed ads found — parser is up to date."

    parser = build_parser()
    updated = 0

    for ad in rows:
        parsed = parse_ad(ad.get("title", ""), ad.get("description", ""), parser)
        from datetime import datetime, timezone
        sb.table("ads").update({
            "specs":              parsed.specs or None,
            "condition":          parsed.condition,
            "seller_notes":       parsed.seller_notes,
            "delivery_available": bool(parsed.delivery_available),
            "seller_type":        parsed.seller_type,
            "llm_parsed_at":      datetime.now(timezone.utc).isoformat(),
        }).eq("ad_url", ad["ad_url"]).execute()
        updated += 1
        time.sleep(4)

    return f"Parser complete: {updated:,} ads processed out of {len(rows):,} fetched."


@tool
def run_deduplication(same_site: bool = False) -> str:
    """
    Run the deduplication agent to find and store duplicate ad pairs.
    Set same_site=False for cross-site duplicates (default, lower threshold).
    Set same_site=True for same-site duplicates (stricter — requires same seller).
    Run cross-site first, then same-site.
    """
    from agents.dedup_agent import find_duplicates

    sb = _sb()
    ads, offset = [], 0
    while True:
        batch = sb.table("ads").select("ad_url, title, price_eur, source, seller_name") \
            .order("ad_url").range(offset, offset + 999).execute().data
        if not batch:
            break
        ads.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000

    pairs = find_duplicates(ads, same_site=same_site)

    for i in range(0, len(pairs), 500):
        sb.table("duplicates").upsert(pairs[i:i+500], on_conflict="ad_url_1,ad_url_2").execute()

    mode = "same-site" if same_site else "cross-site"
    return f"Deduplication ({mode}) complete: {len(pairs):,} duplicate pairs found and stored."


@tool
def run_clustering(dummy: str = "") -> str:
    """
    Run the product clustering agent to group similar ads into product clusters
    using TF-IDF, SVD dimensionality reduction, and MiniBatchKMeans.
    Each ad gets a cluster_id and cluster_label, enabling similar product recommendations.
    Should run after classification so only product ads are considered.
    """
    from agents.clustering_agent import cluster_ads

    sb = _sb()
    ads, offset = [], 0
    while True:
        batch = sb.table("ads").select("ad_url, title, source") \
            .eq("ad_type", "product") \
            .order("ad_url").range(offset, offset + 999).execute().data
        if not batch:
            break
        ads.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000

    results = cluster_ads(ads)

    for i in range(0, len(results), 500):
        sb.table("ads").upsert(results[i:i+500], on_conflict="ad_url").execute()

    cluster_ids = {r["cluster_id"] for r in results}
    return (
        f"Clustering complete: {len(results):,} ads assigned to "
        f"{len(cluster_ids):,} clusters."
    )


# ── Orchestrator ──────────────────────────────────────────────────────────────

_SYSTEM = """You are the orchestrator of a multi-agent system for aggregating electronics ads.
Your job is to coordinate the data processing pipeline by calling the right tools in the right order.

The pipeline has these steps (recommended order):
1. check_pipeline_status — always start here to understand what needs to be done
2. run_classification — label ads as product/service/wanted (fast, run if not done)
3. run_parser — extract specs from descriptions via LLM (slow, run for unparsed ads)
4. run_deduplication (same_site=False) — find cross-site duplicates
5. run_deduplication (same_site=True) — find same-site duplicates
6. run_clustering — group similar products into clusters

Rules:
- Always call check_pipeline_status first.
- Skip steps that are already complete (e.g. if all ads are classified, skip classification).
- Run deduplication twice: first cross-site, then same-site.
- At the end, call check_pipeline_status again to confirm everything is done.
- Summarise what you did and the final state in plain, clear language.
"""


ALL_TOOLS = [
    check_pipeline_status,
    run_classification,
    run_parser,
    run_deduplication,
    run_clustering,
]


def run_orchestrator(parser_limit: int = 200, skip_parser: bool = False) -> str:
    """
    Run the full pipeline orchestrated by the LangChain LLM agent.
    Returns the agent's final summary.
    """
    llm = ChatGroq(model=GROQ_MODEL, api_key=GROQ_API_KEY, temperature=0)
    llm_with_tools = llm.bind_tools(ALL_TOOLS)
    tools_map = {t.name: t for t in ALL_TOOLS}

    task = (
        f"Run the full ad aggregation pipeline. "
        f"For the parser step, process up to {parser_limit} ads. "
        + ("Skip the parser step entirely." if skip_parser else "")
    )

    messages = [
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=task),
    ]

    logger.info("Orchestrator started.")

    while True:
        response = llm_with_tools.invoke(messages)
        messages.append(response)

        if not response.tool_calls:
            # LLM finished — no more tools to call
            break

        for tc in response.tool_calls:
            tool_name = tc["name"]
            tool_args = tc["args"] or {}
            logger.info("→ Calling tool: %s(%s)", tool_name, tool_args)

            try:
                result = tools_map[tool_name].invoke(tool_args)
            except Exception as exc:
                result = f"Error running {tool_name}: {exc}"
                logger.error(result)

            logger.info("← %s: %s", tool_name, str(result)[:120])
            messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

    final = response.content
    logger.info("Orchestrator finished.\n%s", final)
    return final
