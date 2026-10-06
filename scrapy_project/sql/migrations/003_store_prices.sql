-- =====================================================================
-- 003 Референтна цена од македонски продавници
--
-- Наместо LLM-проценката, цената на нов уред сега се зема од продавниците
-- (phones.mk за телефони; Нептун, Сетек, Анхоч, Mobelix и Ledikom за
-- останатото) — ја пополнува populate_store_prices.py.
--   * models добива медијана на цените, бројот на продавници, самите
--     понуди (продавница → цена, наслов, линк) и кога е проверено;
--   * ad_analysis.reference_source прифаќа и 'store';
--   * ads_view за 'store' ја враќа цената од продавница и, на крајот,
--     колона reference_stores со понудите (за „од кои продавници“).
-- Колоните estimated_new_price_mkd / estimated_at остануваат (историја),
-- но новиот код повеќе не ги користи.
-- =====================================================================

set statement_timeout = 0;
begin;

alter table public.models
    add column if not exists store_new_price_mkd numeric,      -- медијана од цените во продавниците
    add column if not exists store_count         integer,      -- во колку продавници е пронајден
    add column if not exists store_sources       jsonb,        -- {"Нептун": {"price": .., "title": .., "url": ..}, ...}
    add column if not exists store_checked_at    timestamptz;  -- кога последно е пребаран

alter table public.ad_analysis
    drop constraint if exists ad_analysis_reference_source_check;
alter table public.ad_analysis
    add constraint ad_analysis_reference_source_check
    check (reference_source in ('store', 'marketplace', 'llm_estimate'));

-- create or replace view смее само да додава колони на крајот,
-- па reference_stores е последна.
create or replace view public.ads_view with (security_invoker = true) as
select
    a.ad_url,
    s.name               as source,
    a.title,
    a.description,
    a.price_amount,
    a.currency,
    a.price_mkd,
    round(a.price_mkd / 61.5, 2) as price_eur,
    c.name               as category,
    l.name               as location,
    a.images,
    a.seller_name,
    a.seller_type,
    a.posted_date,
    a.listing_type,
    a.condition,
    a.specs,
    a.scraped_at,
    a.created_at,
    a.is_active,
    aa.ad_type,
    aa.is_electronics,
    b.name               as brand,
    m.name               as model,
    aa.seller_notes,
    aa.phone,
    aa.delivery_available,
    aa.cluster_id,
    k.label              as cluster_label,
    -- која од цените на моделот важи за огласот, го кажува reference_source
    case aa.reference_source
        when 'store'        then m.store_new_price_mkd
        when 'marketplace'  then m.market_new_price_mkd
        when 'llm_estimate' then m.estimated_new_price_mkd
    end                  as reference_new_price_mkd,
    case aa.reference_source
        when 'store'        then m.store_count
        when 'marketplace'  then m.market_sample_size
        when 'llm_estimate' then 1
    end                  as reference_sample_size,
    aa.reference_source,
    aa.price_vs_new_ratio,
    aa.good_price_deal,
    aa.llm_parsed_at,
    a.source_id,
    a.category_id,
    a.location_id,
    aa.brand_id,
    aa.model_id,
    case when aa.reference_source = 'store' then m.store_sources end as reference_stores
from public.ads a
left join public.sources     s  on s.source_id   = a.source_id
left join public.categories  c  on c.category_id = a.category_id
left join public.locations   l  on l.location_id = a.location_id
left join public.ad_analysis aa on aa.ad_url     = a.ad_url
left join public.brands      b  on b.brand_id    = aa.brand_id
left join public.models      m  on m.model_id    = aa.model_id
left join public.clusters    k  on k.cluster_id  = aa.cluster_id;

-- pipeline_status: колоната „estimated“ (името останува, за да не се
-- менува потписот на функцијата) сега брои модели со цена од продавница.
create or replace function public.pipeline_status()
returns table(total bigint, classified bigint, products bigint, services bigint, wanted bigint,
              parsed bigint, clustered bigint, referenced bigint, duplicate_pairs bigint, estimated bigint)
language sql stable
as $$
    select
        a.total, a.classified, a.products, a.services, a.wanted,
        a.parsed, a.clustered, a.referenced,
        (select count(*) from public.duplicates) as duplicate_pairs,
        (select count(*) from public.models where store_new_price_mkd is not null) as estimated
    from (
        select
            count(*)                                                 as total,
            count(*) filter (where aa.ad_type is not null)           as classified,
            count(*) filter (where aa.ad_type = 'product')           as products,
            count(*) filter (where aa.ad_type = 'service')           as services,
            count(*) filter (where aa.ad_type = 'wanted')            as wanted,
            count(*) filter (where aa.llm_parsed_at is not null)     as parsed,
            count(*) filter (where aa.cluster_id is not null)        as clustered,
            count(*) filter (where aa.price_vs_new_ratio is not null) as referenced
        from public.ads a
        left join public.ad_analysis aa on aa.ad_url = a.ad_url
    ) a;
$$;

commit;
