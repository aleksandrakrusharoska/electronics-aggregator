-- =====================================================================
-- 002 Бришење на старите колони
--
-- Се пушта ДУРИ откако:
--   1. 001_verify.sql покажал 0 изгубени вредности, и
--   2. кодот (spiders, агенти, бекенд) е префрлен на новата шема и
--      поминало барем едно дневно извршување без грешка.
-- Со бришењето на колоните автоматски се бришат и старите индекси врз
-- нив (idx_ads_source, idx_ads_price_eur, idx_ads_pending_parse ...).
-- =====================================================================

set statement_timeout = 0;
begin;

alter table public.ads
    -- заменети со шифрарници (source_id, category_id, location_id)
    drop column source,
    drop column category,
    drop column location,
    -- заменети со price_amount + currency (price_mkd е генерирана)
    drop column price,
    drop column price_eur,
    drop column price_note,
    -- преселени во ad_analysis (бренд, модел и кластер преку ID)
    drop column ad_type,
    drop column is_electronics,
    drop column brand,
    drop column model,
    drop column cluster_id,
    drop column cluster_label,
    drop column seller_notes,
    drop column phone,
    drop column delivery_available,
    drop column reference_source,
    drop column reference_new_price_mkd,
    drop column reference_sample_size,
    drop column price_vs_new_ratio,
    drop column good_price_deal,
    drop column llm_parsed_at;

alter table public.ads alter column source_id set not null;

-- Проценките сега се во models.
drop table public.model_price_estimates;

-- Новите делумни индекси го добиваат конечното име.
alter index idx_ads_null_category_v2     rename to idx_ads_null_category;
alter index idx_ads_null_listing_type_v2 rename to idx_ads_null_listing_type;
alter index idx_ads_null_posted_date_v2  rename to idx_ads_null_posted_date;

commit;
