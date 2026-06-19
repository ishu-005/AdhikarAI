"""Live web-source fetching for answer enrichment (read-only, best-effort)."""
from __future__ import annotations

import io
import re
from urllib.parse import urlparse

import fitz
import requests
from bs4 import BeautifulSoup
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from threading import Lock

from backend.core.logging import get_logger
from backend.core.metrics import metrics
from backend.core.text import load_links_config, normalize_domain, normalize_text

logger = get_logger("web")

_HEADERS = {"User-Agent": "AdhikarAI/2.0 (+legal-assistant)"}
_LIVE_CACHE: dict[str, tuple[list[dict], datetime]] = {}
_LIVE_CACHE_TTL = timedelta(minutes=20)
_LIVE_CACHE_LOCK = Lock()
_TRUSTED_HOST_SUFFIXES = (
    ".gov.in",
    ".nic.in",
    ".mha.gov.in",
    ".indiacode.nic.in",
    ".legislative.gov.in",
    ".nalsa.gov.in",
    ".sci.gov.in",
)


def _is_trusted_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower()
    return any(host == suffix.lstrip(".") or host.endswith(suffix) for suffix in _TRUSTED_HOST_SUFFIXES)


def _cache_key(domain: str, query: str | None) -> str:
    query_part = re.sub(r"\s+", " ", (query or "").strip().lower())[:120]
    return f"{normalize_domain(domain)}::{query_part}"


def _query_terms(query: str | None, fallback_terms: list[str] | None = None) -> list[str]:
    terms = [term.lower() for term in (fallback_terms or []) if term.strip()]
    for token in re.findall(r"[a-z0-9]+", (query or "").lower()):
        if len(token) >= 4 or token in {"fir", "rti", "bnss", "bns"}:
            terms.append(token)
    seen: set[str] = set()
    out: list[str] = []
    for term in terms:
        if term not in seen:
            seen.add(term)
            out.append(term)
    return out


def _best_snippet(text: str, query: str | None = None, fallback_terms: list[str] | None = None, size: int = 700) -> str:
    normalized = normalize_text(text)
    if len(normalized) <= size:
        return normalized
    lower = normalized.lower()
    best_index = -1
    best_weight = -1
    for term in _query_terms(query, fallback_terms):
        index = lower.find(term)
        if index < 0:
            continue
        weight = len(term.split()) * 4 + len(term)
        if weight > best_weight:
            best_index = index
            best_weight = weight
    if best_index < 0:
        return normalized[:size]
    start = max(0, best_index - size // 3)
    end = min(len(normalized), start + size)
    return normalized[start:end].strip()


def fetch_page_text(url: str, timeout: int = 12) -> str:
    resp = requests.get(url, timeout=timeout, headers=_HEADERS)
    resp.raise_for_status()
    content_type = resp.headers.get("content-type", "").lower()
    if url.lower().endswith(".pdf") or "application/pdf" in content_type or resp.content[:5] == b"%PDF-":
        parts: list[str] = []
        with fitz.open(stream=io.BytesIO(resp.content), filetype="pdf") as doc:
            for page in doc:
                parts.append(page.get_text())
        return normalize_text(" ".join(parts))
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    return normalize_text(soup.get_text(separator=" "))


def live_fetch_for_domain(
    domain: str,
    query: str | None = None,
    max_sources: int = 2,
    fallback_terms: list[str] | None = None,
) -> list[dict]:
    query_domain = normalize_domain(domain)
    key = _cache_key(query_domain, query)
    now = datetime.now(UTC)
    with _LIVE_CACHE_LOCK:
        cached = _LIVE_CACHE.get(key)
        if cached and now - cached[1] < _LIVE_CACHE_TTL:
            metrics.incr("live_cache_hit")
            return deepcopy(cached[0])

    links = [
        s
        for s in load_links_config()
        if s.get("enabled", True) is not False
        and normalize_domain(str(s.get("domain", ""))) == query_domain
        and _is_trusted_url(str(s.get("url", "")))
    ][:max_sources]

    fetched: list[dict] = []
    for src in links:
        url, label = src.get("url", ""), src.get("label", "source")
        if not url:
            continue
        try:
            page_text = fetch_page_text(url)
            fetched.append(
                {
                    "label": label,
                    "url": url,
                    "snippet": _best_snippet(page_text, query, fallback_terms),
                    "trusted": True,
                    "official": True,
                    "source_type": "official_legal_web",
                }
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("Live fetch failed for %s: %s", url, exc)
            fetched.append(
                {
                    "label": label,
                    "url": url,
                    "snippet": f"Fetch failed: {exc}",
                    "trusted": True,
                    "official": True,
                    "source_type": "official_legal_web",
                    "fetch_error": True,
                }
            )
    with _LIVE_CACHE_LOCK:
        _LIVE_CACHE[key] = (deepcopy(fetched), now)
    return fetched
