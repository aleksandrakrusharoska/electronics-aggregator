-- Проверки по 001: секоја стара вредност мора да има соодветна нова.
-- Очекувано: сите колони „izgubeni_*“ = 0.

select
    count(*)                                                                                     as oglasi,
    count(*) filter (where nullif(trim(a.source), '')   is not null and a.source_id   is null) as izgubeni_source,
    count(*) filter (where nullif(trim(a.category), '') is not null and a.category_id is null) as izgubeni_category,
    count(*) filter (where nullif(trim(a.location), '') is not null and a.location_id is null) as izgubeni_location,
    count(*) filter (where a.price_eur is not null and a.price_amount is null)                 as izgubeni_ceni,
    count(*) filter (where aa.ad_url is null)                                                   as izgubeni_analizi,
    count(*) filter (where nullif(trim(a.brand), '') is not null and aa.brand_id is null)      as izgubeni_brand,
    count(*) filter (where nullif(trim(a.model), '') is not null and nullif(trim(a.brand), '') is not null
                           and aa.model_id is null)                                             as izgubeni_model,
    count(*) filter (where a.ad_type is distinct from aa.ad_type
                        or a.seller_notes is distinct from aa.seller_notes
                        or a.llm_parsed_at is distinct from aa.llm_parsed_at)                   as izgubeni_agent_polinja
from public.ads a
left join public.ad_analysis aa using (ad_url);

-- Цени вратени од оригиналниот текст (избришани од грешката во парсерот).
-- Очекувано: vrateni_ceni = 4477, valuta_bez_iznos = 0.
select
    count(*) filter (where price_eur is null and price_amount is not null) as vrateni_ceni,
    count(*) filter (where currency is not null and price_amount is null)  as valuta_bez_iznos
from public.ads;

-- Генерираната price_mkd наспроти старата (преку price_eur): разлика над 1 ден.
select count(*) as razlicni_ceni
from public.ads
where price_eur is not null and abs(price_mkd - price_eur * 61.5) > 1 and currency = 'EUR';

-- Големина на шифрарниците и огласот во рамен облик.
select 'sources' as tabela, count(*) from public.sources
union all select 'categories',  count(*) from public.categories
union all select 'locations',   count(*) from public.locations
union all select 'brands',      count(*) from public.brands
union all select 'models',      count(*) from public.models
union all select 'clusters',    count(*) from public.clusters
union all select 'ad_analysis', count(*) from public.ad_analysis
union all select 'duplicates',  count(*) from public.duplicates
union all select 'ads_view',    count(*) from public.ads_view
union all select 'modeli_so_procenka', count(*) from public.models where estimated_new_price_mkd is not null
union all select 'procenki_vo_stariot_kesh', count(*) from public.model_price_estimates;

-- Референтната цена во ads_view наспроти старата колона (без Setec).
-- Разлики се очекуваат само кај огласите на 9-те модели со застарени
-- пазарни вредности.
select count(*) as razlicni_referentni_ceni
from public.ads a
join public.ads_view v using (ad_url)
where a.reference_source in ('marketplace', 'llm_estimate')
  and a.reference_new_price_mkd is distinct from v.reference_new_price_mkd;

select * from public.pipeline_status();
