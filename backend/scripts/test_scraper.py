"""Брз тест на еден scraper адаптер — без база, без Celery.

Употреба (од backend/ фолдерот):
    python scripts/test_scraper.py reklama5
    python scripts/test_scraper.py pazar3
    python scripts/test_scraper.py reklama5 --limit 10

Печати колку огласи се собрани и примери, за брза проверка дали
URL шаблоните и екстракцијата работат на живиот портал.
"""
import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("portal", choices=["reklama5", "pazar3"])
    parser.add_argument("--limit", type=int, default=5, help="Колку примери да прикаже")
    args = parser.parse_args()

    if args.portal == "reklama5":
        from app.agents.scrapers.reklama5 import scrape_reklama5 as fn
    else:
        from app.agents.scrapers.pazar3 import scrape_pazar3 as fn

    items = fn()

    print(f"\n{'=' * 60}")
    print(f"Портал: {args.portal}  |  Собрани: {len(items)} уникатни огласи")
    print(f"{'=' * 60}")

    with_price = sum(1 for i in items if i.get("price") is not None)
    print(f"Со цена: {with_price}/{len(items)}")

    for item in items[: args.limit]:
        print("-" * 60)
        print(json.dumps(item, ensure_ascii=False, indent=2))

    if not items:
        print("\n⚠ Нема резултати. Најчести причини:")
        print("  1. URL шаблоните не се точни — отвори го порталот и провери")
        print("  2. Порталот бара JavaScript → провери дали Playwright е инсталиран:")
        print("     pip install playwright && playwright install chromium")
        print("  3. Порталот блокира — провери го одговорот со:")
        print("     python -c \"import httpx; print(httpx.get('https://www.reklama5.mk').status_code)\"")


if __name__ == "__main__":
    main()
