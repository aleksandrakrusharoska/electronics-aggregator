"""Scraper Agent — собира огласи од јавни портали.

Секој портал има свој адаптер во app/agents/scrapers/.
Адаптерите враќаат листа dict-ови со унифицирана шема (Listing полиња).

ВАЖНО (и за трудот): почитувај robots.txt, rate limiting и услови
за користење на порталите. Идентификувај се со чесен User-Agent.
"""
from app.agents.scrapers.pazar3 import scrape_pazar3
from app.agents.scrapers.reklama5 import scrape_reklama5
from app.core.agent_log import log_activity
from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.listing import Listing, PriceHistory

SCRAPERS = {
    "reklama5": scrape_reklama5,
    "pazar3": scrape_pazar3,
}


@celery_app.task(name="agents.scraper.scrape_all")
def scrape_all(_prev=None) -> dict:
    """Ги извршува сите адаптери и запишува нови огласи во базата."""
    new_ids: list[int] = []
    db = SessionLocal()
    try:
        for name, fn in SCRAPERS.items():
            log_activity("ScraperAgent", f"Скенирам портал: {name}", target="System")
            try:
                items = fn()
            except Exception as exc:  # порталот не смее да го сруши целиот циклус
                log_activity("ScraperAgent", f"Грешка кај {name}: {exc}", level="error")
                continue

            added = 0
            for item in items:
                exists = db.query(Listing).filter_by(source_url=item["source_url"]).first()
                if exists:
                    # промена на цена → историја + ажурирање
                    new_price = item.get("price")
                    if new_price is not None and new_price != exists.price:
                        db.add(PriceHistory(listing_id=exists.id, price=new_price))
                        exists.price = new_price
                    continue
                listing = Listing(**item)
                db.add(listing)
                db.flush()
                if listing.price is not None:
                    db.add(PriceHistory(listing_id=listing.id, price=listing.price))
                new_ids.append(listing.id)
                added += 1
            db.commit()
            log_activity("ScraperAgent", f"{name}: {added} нови огласи", target="De-duplicator")
    finally:
        db.close()

    return {"new_listing_ids": new_ids}
