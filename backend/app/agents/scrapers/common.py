"""Заеднички алатки за сите scraper адаптери.

Техники преземени/адаптирани од SetecCrawlerService.java:
- throttle() меѓу барања (rate limiting, чесен User-Agent)
- хеуристичка детекција на продукт-картички (отпорна на редизајн)
- ценовна екстракција со regex (мин. вредност >= 100 MKD)
- scroll-until-stable за JavaScript-рендерирани страници

Генеричкиот extract_cards() е портал-агностичен: секој адаптер само
задава URL шаблони и мали специфики.
"""
import logging
import re
import time
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup, Tag

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# 24.999 / 24 999 / 24999(,50) — иста шема како кај Java верзијата
PRICE_PATTERN = re.compile(r"(?<!\d)(\d{1,3}(?:[.\s]\d{3})*|\d+)(?:,\d+)?(?!\d)")

CARD_SELECTORS = (
    ".product, .product-item, .product-list-item, .item, article, li, "
    "div[class*=product], div[class*=ad], div[class*=oglas], "
    "div[class*=grid] > div, main a[href]"
)

TITLE_SELECTORS = ".title, .product-title, .name, .ad-title, h1, h2, h3, h4"

_last_request: float = 0.0


def throttle(delay_ms: int = 750) -> None:
    """Минимум delay_ms меѓу два HTTP повика."""
    global _last_request
    elapsed = (time.monotonic() - _last_request) * 1000
    if elapsed < delay_ms:
        time.sleep((delay_ms - elapsed) / 1000)
    _last_request = time.monotonic()


def normalize(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", s.replace("\u00a0", " ")).strip()


def extract_price(text: str) -> float | None:
    """Најмала вредност >= 100 = цената (филтрира '24 месеци' и сл. шум;
    од редовна и акциска цена ја зема пониската)."""
    best: float | None = None
    for m in PRICE_PATTERN.finditer(text.replace(",", "")):
        try:
            value = float(m.group(1).replace(".", "").replace(" ", ""))
        except ValueError:
            continue
        if value >= 100 and (best is None or value < best):
            best = value
    return best


def looks_like_product_card(card: Tag, text: str) -> bool:
    """Хеуристика наместо тврди селектори: линк + (слика или цена)."""
    has_link = card.select_one("a[href]") is not None
    has_image = card.select_one("img") is not None
    has_price = bool(PRICE_PATTERN.search(text)) or card.select_one("[class*=price], .price, .cena") is not None
    return has_link and (has_image or has_price)


def clean_title(title: str, max_len: int = 140) -> str:
    title = re.sub(r"(?i)(club|клуб)\s*(price|цена).*$", "", title).strip()
    title = re.sub(r"(?i)(regular|редовна)\s*(price|цена).*$", "", title).strip()
    title = re.sub(r"\s+\d{1,3}(?:[.\s]\d{3})*\s*(?:ден|den|mkd|€|eur).*$", "", title, flags=re.I).strip()
    return title[:max_len]


def guess_brand(title: str) -> str | None:
    if not title:
        return None
    first = re.sub(r"[^\w\-]", "", title.split()[0], flags=re.UNICODE)
    return first.upper() if first else None


def fetch_html(url: str, timeout_ms: int | None = None) -> str:
    """Обичен HTTP fetch (за server-side рендерирани портали)."""
    settings = get_settings()
    resp = httpx.get(
        url,
        headers={"User-Agent": settings.scrape_user_agent, "Accept-Language": "mk,en;q=0.8"},
        timeout=(timeout_ms or 10_000) / 1000,
        follow_redirects=True,
        proxy=settings.proxy_url or None,
    )
    resp.raise_for_status()
    return resp.text


def fetch_rendered(url: str, scroll_pause_ms: int = 600) -> str:
    """Playwright fetch за JavaScript-рендерирани страници,
    со scroll-until-stable (порт на scrollUntilContentStopsGrowing)."""
    from playwright.sync_api import sync_playwright  # lazy import

    settings = get_settings()
    launch_kwargs = {"headless": True}
    if settings.proxy_url:
        parts = urlsplit(settings.proxy_url)
        launch_kwargs["proxy"] = {
            "server": f"{parts.scheme}://{parts.hostname}:{parts.port}",
            "username": parts.username or "",
            "password": parts.password or "",
        }
    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_kwargs)
        page = browser.new_page(user_agent=settings.scrape_user_agent)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            try:
                page.wait_for_load_state("networkidle", timeout=20_000)
            except Exception:
                pass  # продолжи со најдоброто достапно DOM (како кај проф.)

            previous_height, stable = -1, 0
            for _ in range(8):
                if stable >= 2:
                    break
                height = page.evaluate(
                    "Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)"
                )
                page.evaluate("h => window.scrollTo(0, h)", height)
                page.wait_for_timeout(scroll_pause_ms)
                new_height = page.evaluate(
                    "Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)"
                )
                stable = stable + 1 if new_height in (previous_height, height) else 0
                previous_height = new_height

            return page.content()
        finally:
            browser.close()


def extract_cards(
    html: str,
    *,
    source: str,
    base_url: str,
    require_domain: str,
    link_hint: str | None = None,
    skip_url_parts: tuple[str, ...] = (),
    default_currency: str = "MKD",
) -> list[dict]:
    """Генеричка хеуристичка екстракција на огласи од HTML.

    Порт на extractProductCards(): широки кандидат-селектори +
    looks_like_product_card филтер + дедупликација по URL.
    """
    soup = BeautifulSoup(html, "html.parser")
    candidates = soup.select(CARD_SELECTORS) or soup.select("a[href]")

    seen: set[str] = set()
    out: list[dict] = []

    for card in candidates:
        text = normalize(card.get_text(" "))
        if len(text) < 8 or not looks_like_product_card(card, text):
            continue

        link = None
        if link_hint:
            link = card.select_one(f"a[href*='{link_hint}']")
        if link is None:
            link = next((a for a in card.select("a[href]") if a.select_one("img")), None)
        if link is None:
            link = card.select_one("a[href]")
        if link is None:
            continue

        href = link.get("href", "")
        if href.startswith("/"):
            href = base_url.rstrip("/") + href
        if (
            not href
            or require_domain not in href
            or any(part in href for part in skip_url_parts)
            or href in seen
        ):
            continue
        seen.add(href)

        title_el = card.select_one(TITLE_SELECTORS)
        if title_el is not None:
            raw_title = title_el.get_text(" ")
        else:
            img_alt = card.select_one("img[alt]")
            raw_title = img_alt["alt"] if img_alt and img_alt.get("alt") else link.get_text(" ")
        title = clean_title(normalize(raw_title))
        if not title or len(title) < 3:
            continue

        img = card.select_one("img[src], img[data-src]")
        image_url = ""
        if img is not None:
            image_url = img.get("src") or img.get("data-src") or ""
            if image_url.startswith("/"):
                image_url = base_url.rstrip("/") + image_url

        out.append(
            {
                "source": source,
                "source_url": href,
                "title": title,
                "description": text[:500],
                "brand": guess_brand(title),
                "price": extract_price(text),
                "currency": default_currency,
                "image_url": image_url or None,
            }
        )

    return out


def crawl_pages(
    url_templates: list[str],
    *,
    max_pages: int,
    fetch,
    extract,
    delay_ms: int = 750,
) -> list[dict]:
    """Заеднички циклус: категории × страници, со throttle и заштита од паѓање."""
    items: list[dict] = []
    for template in url_templates:
        for page_num in range(1, max_pages + 1):
            throttle(delay_ms)
            url = template.format(page=page_num)
            try:
                html = fetch(url)
            except Exception as exc:
                logger.warning("Неуспешно вчитување %s: %s", url, exc)
                break
            cards = extract(html)
            if not cards:
                break
            items.extend(cards)

    unique = {item["source_url"]: item for item in items}
    return list(unique.values())
