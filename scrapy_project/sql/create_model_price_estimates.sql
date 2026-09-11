-- New table: cached LLM-estimated "new" price per unique brand+model,
-- used as a third fallback tier in reference_price_agent.py when neither
-- Setec's retail catalog nor our own marketplace New-condition listings
-- have a match. Cached per model (not per ad) so many ads sharing the
-- same brand+model reuse a single estimate instead of one LLM call each.
create table if not exists model_price_estimates (
    brand text not null,
    model text not null,
    estimated_new_price_mkd numeric,
    estimated_at timestamptz not null default now(),
    primary key (brand, model)
);

-- Case-insensitive lookups match how reference_price_agent.py normalizes
-- brand/model (lowercased) before comparing.
create index if not exists idx_model_price_estimates_lower
    on model_price_estimates (lower(brand), lower(model));
