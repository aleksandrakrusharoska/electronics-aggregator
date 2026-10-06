-- =====================================================================
-- 004 Групи на дупликати
--
-- Дупликатите (duplicates) се парови; во апликацијата се прикажува по
-- еден оглас за сите огласи на ист продавач за ист уред (на двата портали
-- или повторно објавен на истиот), со линкови до сите. run_dedup_agent.py
-- ги спојува паровите во групи и на секој оглас во група му запишува:
--   dup_group_id  иста вредност за сите огласи од групата
--   dup_primary   true само за огласот што се прикажува во листата
--                 (најевтиниот; при иста цена, најновиот)
-- Оглас без дупликат ги има двете колони празни (null).
-- =====================================================================

set statement_timeout = 0;
begin;

alter table public.ad_analysis
    add column if not exists dup_group_id bigint,
    add column if not exists dup_primary  boolean;

create index if not exists idx_ad_analysis_dup_group
    on public.ad_analysis (dup_group_id) where dup_group_id is not null;

-- create or replace view смее само да додава колони на крајот
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
    case when aa.reference_source = 'store' then m.store_sources end as reference_stores,
    aa.dup_group_id,
    aa.dup_primary
from public.ads a
left join public.sources     s  on s.source_id   = a.source_id
left join public.categories  c  on c.category_id = a.category_id
left join public.locations   l  on l.location_id = a.location_id
left join public.ad_analysis aa on aa.ad_url     = a.ad_url
left join public.brands      b  on b.brand_id    = aa.brand_id
left join public.models      m  on m.model_id    = aa.model_id
left join public.clusters    k  on k.cluster_id  = aa.cluster_id;

commit;
