-- Single round-trip replacement for the 10 sequential count(exact=True)
-- queries previously issued by check_pipeline_status() in orchestrator_agent.py.
-- Each of those queries did its own scan/filter over the `ads` table
-- (71k+ rows), and issuing them one after another was enough to trip a
-- Postgres statement timeout under load. This function computes the six
-- `ads`-derived counts in a single pass (FILTER clauses over one scan)
-- and folds in the two small-table counts, so the whole status check is
-- one query instead of ten.
create or replace function pipeline_status()
returns table (
    total bigint,
    classified bigint,
    products bigint,
    services bigint,
    wanted bigint,
    parsed bigint,
    clustered bigint,
    referenced bigint,
    duplicate_pairs bigint,
    estimated bigint
)
language sql
stable
as $$
    select
        a.total, a.classified, a.products, a.services, a.wanted,
        a.parsed, a.clustered, a.referenced,
        (select count(*) from duplicates) as duplicate_pairs,
        (select count(*) from model_price_estimates) as estimated
    from (
        select
            count(*) as total,
            count(*) filter (where ad_type is not null) as classified,
            count(*) filter (where ad_type = 'product') as products,
            count(*) filter (where ad_type = 'service') as services,
            count(*) filter (where ad_type = 'wanted') as wanted,
            count(*) filter (where specs is not null) as parsed,
            count(*) filter (where cluster_id is not null) as clustered,
            count(*) filter (where reference_source is not null) as referenced
        from ads
    ) a;
$$;
