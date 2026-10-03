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

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from groq import BadRequestError
from langchain_groq import ChatGroq
from supabase import create_client

from lookups import upsert_rows

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
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
    # Single round trip via the pipeline_status() Postgres function
    # (scrapy_project/sql/create_pipeline_status_function.sql) instead of
    # 10 sequential count(exact=True) queries — the previous version could
    # trip a statement timeout under load since each count re-scanned/
    # filtered the 71k+-row `ads` table on its own.
    row = sb.rpc("pipeline_status").execute().data[0]
    total      = row["total"] or 0
    classified = row["classified"] or 0
    parsed     = row["parsed"] or 0
    duplicates = row["duplicate_pairs"] or 0
    clustered  = row["clustered"] or 0
    estimated  = row["estimated"] or 0
    referenced = row["referenced"] or 0
    products   = row["products"] or 0
    services   = row["services"] or 0
    wanted     = row["wanted"] or 0

    return (
        f"Pipeline status:\n"
        f"  Total ads:       {total:,}\n"
        f"  Classified:      {classified:,} ({100*classified//total if total else 0}%) "
        f"[product={products:,}, service={services:,}, wanted={wanted:,}]\n"
        f"  LLM-parsed:      {parsed:,} ({100*parsed//total if total else 0}%)\n"
        f"  Duplicate pairs: {duplicates:,}\n"
        f"  Clustered:       {clustered:,} ({100*clustered//total if total else 0}%)\n"
        f"  Model estimates:  {estimated:,}\n"
        f"  Price references: {referenced:,}\n"
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
    ads, last_url = [], None
    while True:
        q = sb.table("ads").select("ad_url, title, description").order("ad_url")
        if last_url is not None:
            q = q.gt("ad_url", last_url)
        batch = q.limit(1000).execute().data
        if not batch:
            break
        ads.extend(batch)
        if len(batch) < 1000:
            break
        last_url = batch[-1]["ad_url"]

    results = classify_ads(ads)
    upsert_rows(sb, "ad_analysis", results, on_conflict="ad_url")

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
    # Same code path as the parse_ads workflow (run_parser_agent.run), so
    # the daily pipeline also writes brand/model/is_electronics and price
    # corrections. It used to write only specs/condition/notes here, leaving
    # brand and model empty on most newly scraped ads.
    from run_parser_agent import run as run_parser_agent

    processed = run_parser_agent(_sb(), limit=limit)
    if not processed:
        return "No unparsed ads found (or all LLM providers exhausted) — parser is up to date."
    return f"Parser complete: {processed:,} ads processed."


@tool
def run_deduplication(same_site: bool = False) -> str:
    """
    Run the deduplication agent to find and store duplicate ad pairs.
    Set same_site=False for cross-site duplicates (default, lower threshold).
    Set same_site=True for same-site duplicates (stricter — requires same seller).
    Run cross-site first, then same-site.
    """
    # Same code path as run_dedup_agent.py. This tool used to import a
    # find_duplicates() that dedup_agent never had, so deduplication failed
    # with an ImportError on every orchestrated run.
    from agents.dedup_agent import find_cross_site_duplicates, find_same_site_duplicates
    from run_dedup_agent import fetch_ads, store

    sb = _sb()
    r5, p3 = fetch_ads(sb, "reklama5"), fetch_ads(sb, "pazar3")
    if same_site:
        pairs = find_same_site_duplicates(r5) + find_same_site_duplicates(p3)
    else:
        pairs = find_cross_site_duplicates(r5, p3)
    store(sb, pairs)

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
    from agents.clustering_agent import cluster_ads, save_clusters

    sb = _sb()
    ads, last_url = [], None
    while True:
        q = sb.table("ads_view").select("ad_url, title").eq("ad_type", "product").order("ad_url")
        if last_url is not None:
            q = q.gt("ad_url", last_url)
        batch = q.limit(1000).execute().data
        if not batch:
            break
        ads.extend(batch)
        if len(batch) < 1000:
            break
        last_url = batch[-1]["ad_url"]

    results = cluster_ads(ads)
    cluster_ids = save_clusters(sb, ads, results)
    return (
        f"Clustering complete: {len(results):,} ads assigned to "
        f"{len(cluster_ids):,} clusters."
    )


@tool
def run_price_estimates(dummy: str = "") -> str:
    """
    Populate the cached LLM new-price estimates for distinct brand/model pairs.
    Must run before run_reference_prices.
    """
    from populate_price_estimates import main

    main()
    return "LLM price-estimate cache populated successfully."


@tool
def run_reference_prices(dummy: str = "") -> str:
    """
    Compute reference prices and good-deal flags using marketplace listings
    and cached LLM estimates. No external retailer scraping is used.
    """
    from run_reference_price_agent import main

    main()
    return "Reference prices and good-deal flags computed successfully."


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
7. run_price_estimates — estimate new prices with the LLM
8. run_reference_prices — calculate deal ratios and flags

Rules:
- Always call check_pipeline_status first.
- Skip steps that are already complete (e.g. if all ads are classified, skip classification).
- Run deduplication twice: first cross-site, then same-site.
- Run price estimates before reference prices.
- At the end, call check_pipeline_status again to confirm everything is done.
- Summarise what you did and the final state in plain, clear language.
"""


ALL_TOOLS = [
    check_pipeline_status,
    run_classification,
    run_parser,
    run_deduplication,
    run_clustering,
    run_price_estimates,
    run_reference_prices,
]


class _Step:
    def __init__(self, label, tool, args=lambda limit: {}):
        self.label, self.tool, self.args = label, tool, args
        self.key = _step_key(tool, args(0))


def _step_key(tool_name: str, tool_args: dict) -> str:
    # Deduplication is one tool run twice, so its two steps differ by argument.
    if tool_name == "run_deduplication":
        return f"run_deduplication:{'same' if tool_args.get('same_site') else 'cross'}"
    return tool_name


# The pipeline in its dependency order (as in _SYSTEM). The model chooses
# what to run; this list is only what "finished" means, and the order used
# for any steps it leaves out.
PIPELINE_STEPS = [
    _Step("classification", "run_classification"),
    _Step("parser", "run_parser", lambda limit: {"limit": limit}),
    _Step("cross-site deduplication", "run_deduplication", lambda limit: {"same_site": False}),
    _Step("same-site deduplication", "run_deduplication", lambda limit: {"same_site": True}),
    _Step("clustering", "run_clustering"),
    _Step("price estimates", "run_price_estimates"),
    _Step("reference prices", "run_reference_prices"),
]
MAX_REMINDERS = 2


def run_orchestrator(parser_limit: int = 200, skip_parser: bool = False) -> str:
    """
    Run the full pipeline orchestrated by the LangChain LLM agent.
    Returns the agent's final summary.
    """
    # One tool call per model turn keeps the dependency order explicit:
    # estimates must finish before reference prices can be computed.
    def _bind(temperature):
        llm = ChatGroq(model=GROQ_MODEL, api_key=GROQ_API_KEY, temperature=temperature)
        return llm.bind_tools(ALL_TOOLS, parallel_tool_calls=False)

    llm_with_tools = _bind(0)
    # Groq occasionally rejects the model's own tool call as unparseable
    # (400 "tool_use_failed"), which used to end the whole run midway
    # (2026-09-29: after dedup, before classification). At temperature 0 the
    # same prompt tends to reproduce the same bad output, so retries sample.
    llm_retry = _bind(0.5)
    tools_map = {t.name: t for t in ALL_TOOLS}

    def _invoke(msgs, attempts=3):
        for attempt in range(1, attempts + 1):
            try:
                return (llm_with_tools if attempt == 1 else llm_retry).invoke(msgs)
            except BadRequestError as exc:
                if "tool_use_failed" not in str(exc) and "Parsing failed" not in str(exc):
                    raise
                if attempt == attempts:
                    raise
                logger.warning("Model produced an unparseable tool call (attempt %d/%d), retrying.",
                               attempt, attempts)

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

    steps = [s for s in PIPELINE_STEPS if not (skip_parser and s.tool == "run_parser")]
    done: set[str] = set()
    reminders = 0
    final = ""

    def _call(tool_name, tool_args):
        logger.info("→ Calling tool: %s(%s)", tool_name, tool_args)
        try:
            result = tools_map[tool_name].invoke(tool_args)
        except Exception as exc:
            result = f"Error running {tool_name}: {exc}"
            logger.error(result)
        logger.info("← %s: %s", tool_name, str(result)[:120])
        done.add(_step_key(tool_name, tool_args))
        return result

    while True:
        try:
            response = _invoke(messages)
        except BadRequestError as exc:
            logger.error("Model kept failing (%s); finishing the remaining steps without it.", exc)
            break
        messages.append(response)

        if not response.tool_calls:
            missing = [s for s in steps if s.key not in done]
            # The model decides when it is done, and it has stopped halfway
            # with an empty answer (2026-09-29, after cross-site dedup while
            # Groq was rate limiting). Remind it what is left, twice at most.
            if missing and reminders < MAX_REMINDERS:
                reminders += 1
                logger.warning("Model stopped with steps not run (%s), reminder %d/%d.",
                               ", ".join(s.label for s in missing), reminders, MAX_REMINDERS)
                messages.append(HumanMessage(content=(
                    "The pipeline is not finished. Not run yet in this session: "
                    + ", ".join(s.label for s in missing)
                    + ". Run the ones that are still needed (check_pipeline_status shows the "
                    "current state), then summarise.")))
                continue
            final = response.content
            break

        for tc in response.tool_calls:
            result = _call(tc["name"], tc["args"] or {})
            messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

    # Fallback: whatever the model did not get to runs in the fixed order,
    # so a misbehaving model can delay the pipeline but not leave it half
    # done (clustering and reference prices were skipped 2026-09-29..10-02).
    missing = [s for s in steps if s.key not in done]
    if missing:
        logger.warning("Running %d remaining step(s) in the default order: %s",
                       len(missing), ", ".join(s.label for s in missing))
        for s in missing:
            _call(s.tool, s.args(parser_limit))
        final = (final + "\n\n" if final else "") + (
            "Finished without the model: " + ", ".join(s.label for s in missing) + ".")

    logger.info("Orchestrator finished.\n%s", final)
    return final
