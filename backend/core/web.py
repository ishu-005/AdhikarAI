"""Live web-source fetching for answer enrichment (read-only, best-effort)."""
from __future__ import annotations

import requests
from bs4 import BeautifulSoup
from datetime import UTC, datetime, timedelta

from backend.core.logging import get_logger
from backend.core.metrics import metrics
from backend.core.text import load_links_config, normalize_domain, normalize_text

logger = get_logger("web")

_HEADERS = {"User-Agent": "AdhikarAI/2.0 (+legal-assistant)"}
_LIVE_CACHE: dict[str, tuple[list[dict], datetime]] = {}
_LIVE_CACHE_TTL = timedelta(minutes=20)


def fetch_page_text(url: str, timeout: int = 12) -> str:
    resp = requests.get(url, timeout=timeout, headers=_HEADERS)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    return normalize_text(soup.get_text(separator=" "))


def live_fetch_for_domain(domain: str, max_sources: int = 2) -> list[dict]:
    query_domain = normalize_domain(domain)
    now = datetime.now(UTC)
    cached = _LIVE_CACHE.get(query_domain)
    if cached and now - cached[1] < _LIVE_CACHE_TTL:
        metrics.incr("live_cache_hit")
        return [dict(item) for item in cached[0]]

    links = [
        s
        for s in load_links_config()
        if s.get("enabled", True) is not False
        and normalize_domain(str(s.get("domain", ""))) == query_domain
    ][:max_sources]

    fetched: list[dict] = []
    for src in links:
        url, label = src.get("url", ""), src.get("label", "source")
        if not url:
            continue
        try:
            fetched.append({"label": label, "url": url, "snippet": fetch_page_text(url)[:700]})
        except Exception as exc:  # noqa: BLE001
            logger.info("Live fetch failed for %s: %s", url, exc)
            fetched.append({"label": label, "url": url, "snippet": f"Fetch failed: {exc}"})
    _LIVE_CACHE[query_domain] = ([dict(item) for item in fetched], now)
    return fetched
