"""
LLM-based "new" price estimator for brand+model pairs that neither
Setec's retail catalog nor our own marketplace New-condition listings
cover (see reference_price_agent.py's tier 1/2). Cached per unique
brand+model in the model_price_estimates table — many ads share a model,
so this is one LLM call per unique model, not per ad.

Reuses parser_agent's provider rotation (13 providers as of today: 11
Groq + 2 Gemini, reasoning_effort='low', same daily-exhaustion handling)
rather than building a separate one.
"""
import json
import logging
import re

from agents.parser_agent import AllProvidersExhausted, RotatingParser, _extract_text, _mark_if_daily_exhausted, build_parser

logger = logging.getLogger(__name__)

# The bigger model, not the default 20b: measured directly on the same
# test set — 120b estimated a case 20b gave up on (returned null) and gave
# more differentiated prices across items, at essentially the same token
# cost (~640 tokens/call either way, since reasoning_effort='low' is what
# actually controls output length, not model size). This task's total
# volume (one call per unique brand+model, not per ad) is small enough
# that the bigger model's cost is a non-issue either way.
PRICE_ESTIMATE_MODEL = "openai/gpt-oss-120b"


def build_price_estimate_parser() -> RotatingParser:
    return build_parser(groq_model=PRICE_ESTIMATE_MODEL)

_SYSTEM_BATCH = """You estimate the approximate CURRENT retail price, in Macedonian denars (MKD), of a brand-new unit of each electronics product listed below, as sold in North Macedonia today.

You will receive a JSON array where each element has "i" (an integer index), "brand", and "model".
Return ONLY a valid JSON array — no markdown, no code blocks, no explanation — with exactly one object per input item, in the same order, each carrying its original "i" plus:
  "price_mkd": your best-estimate price in MKD as a plain number (no currency symbol, no thousands separator), or null if you don't recognize this product well enough to estimate confidently.

Rules:
- Estimate the price of a NEW, currently- or recently-sold unit — not a used one, not a historical launch price if the product is old and discounted now.
- If the exact model is discontinued, estimate what it would realistically cost today (e.g. a used/refurb market floor, or a closely comparable current model), not its price when new-in-2015.
- Use null rather than guessing wildly for something you don't recognize (a typo, a non-existent model, a non-electronics item that slipped in).
- Never explain your reasoning in the output — only the JSON.

Each output array element must have exactly this structure:
{"i": 0, "price_mkd": 12000}"""


def _parse_json_array_response(raw: str) -> list:
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    opens_c, closes_c = raw.count('{'), raw.count('}')
    opens_b, closes_b = raw.count('['), raw.count(']')
    patched = raw + '}' * max(0, opens_c - closes_c) + ']' * max(0, opens_b - closes_b)
    try:
        data = json.loads(patched)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    cut = raw.rfind('},')
    if cut != -1:
        data = json.loads(raw[:cut + 1] + ']')
        if isinstance(data, list):
            return data
    raise ValueError(f"Could not parse JSON array from: {raw[:200]!r}")


def _coerce_price(value) -> float | None:
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    if isinstance(value, str):
        try:
            n = float(re.sub(r'[^\d.]', '', value.replace(',', '.')))
            return n if n > 0 else None
        except ValueError:
            return None
    return None


def estimate_prices_batch(pairs: list[tuple[str, str]], parser: RotatingParser = None) -> list[float | None]:
    """pairs: list of (brand, model). Returns estimated_new_price_mkd (or
    None) in the same order, one LLM call for the whole batch."""
    if parser is None:
        parser = build_price_estimate_parser()
    if not pairs:
        return []

    payload = [{"i": i, "brand": b, "model": m} for i, (b, m) in enumerate(pairs)]
    messages = [
        {"role": "system", "content": _SYSTEM_BATCH},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]

    for _ in range(len(parser._clients)):
        name, client = parser.next()
        try:
            response = client.invoke(messages)
            raw = _extract_text(response.content).strip()
            raw = re.sub(r'^```(?:json)?\s*', '', raw)
            raw = re.sub(r'\s*```$', '', raw)
            results_raw = _parse_json_array_response(raw)

            by_index = {}
            for entry in results_raw:
                if isinstance(entry, dict) and isinstance(entry.get("i"), int):
                    by_index[entry["i"]] = entry

            prices = []
            for i in range(len(pairs)):
                data = by_index.get(i)
                prices.append(_coerce_price(data.get("price_mkd")) if data else None)

            logger.debug("Estimated batch of %d via %s", len(pairs), name)
            return prices
        except Exception as exc:
            if not _mark_if_daily_exhausted(parser, name, exc):
                logger.warning("Price estimate batch failed (%s) for %d pairs: %s — trying next provider",
                                name, len(pairs), exc)

    # Every provider errored on this batch (not necessarily daily-exhausted —
    # could be transient failures across the board). Raise rather than
    # returning [None]*len(pairs): this result gets cached permanently by
    # populate_price_estimates.py, so silently returning "unrecognized" here
    # would wrongly freeze in a null for pairs the LLM never actually saw.
    raise AllProvidersExhausted(f"All providers failed for price-estimate batch of {len(pairs)} pairs")
