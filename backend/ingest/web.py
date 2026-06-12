"""Scheduled crawl of dynamic web sources with hash-based change detection."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime

import requests
import urllib3
from apscheduler.schedulers.background import BackgroundScheduler
from bs4 import BeautifulSoup

from backend.core.clients import get_supabase_client
from backend.core.config import resolve_path
from backend.core.logging import get_logger
from backend.core.text import load_links_config
from backend.ingest.store import embed_and_store

logger = get_logger("ingest.web")

HASH_FILE = resolve_path("crawl_hashes.json")
ALLOW_INSECURE_SSL = os.getenv("ALLOW_INSECURE_SSL", "false").lower() == "true"
if ALLOW_INSECURE_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _load_hashes() -> dict:
    if not HASH_FILE.exists() or HASH_FILE.stat().st_size == 0:
        return {}
    try:
        return json.loads(HASH_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("crawl_hashes.json invalid; starting fresh.")
        return {}


def _save_hashes(h: dict) -> None:
    HASH_FILE.write_text(json.dumps(h, indent=2), encoding="utf-8")


def fetch_and_clean(url: str) -> str:
    try:
        resp = requests.get(url, timeout=15, headers=_HEADERS)
    except requests.exceptions.SSLError:
        if not ALLOW_INSECURE_SSL:
            raise
        logger.warning("Retrying with SSL verification disabled for %s", url)
        resp = requests.get(url, timeout=15, headers=_HEADERS, verify=False)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    return " ".join(soup.get_text(separator=" ").split())


def chunk_text(text: str, size: int = 500, overlap: int = 50) -> list[str]:
    words = text.split()
    chunks, i = [], 0
    while i < len(words):
        chunks.append(" ".join(words[i : i + size]))
        i += size - overlap
    return [c for c in chunks if len(c) > 100]


def crawl_dynamic_sources() -> None:
    hashes = _load_hashes()
    client = get_supabase_client()

    for source in load_links_config():
        if source.get("enabled", True) is False:
            continue
        url = source.get("url")
        if not url:
            continue
        domain = source.get("domain", "general")
        label = source.get("label", "source")
        logger.info("[WEB] checking %s ...", label)
        try:
            text = fetch_and_clean(url)
            new_hash = hashlib.md5(text.encode()).hexdigest()
            if hashes.get(url) == new_hash:
                logger.info("  no change - skipping")
                continue
            if client is not None:
                client.table("legal_documents").delete().eq("url", url).execute()
            chunks = chunk_text(text)
            metas = [
                {
                    "source": "web",
                    "url": url,
                    "domain": domain,
                    "label": label,
                    "ingested_at": datetime.now(UTC).isoformat(),
                }
                for _ in chunks
            ]
            embed_and_store(chunks, metas)
            hashes[url] = new_hash
            logger.info("  updated %s -> %d chunks", label, len(chunks))
        except Exception as exc:  # noqa: BLE001
            logger.warning("  ERROR on %s: %s", url, exc)
    _save_hashes(hashes)


def start_scheduler() -> BackgroundScheduler:
    interval_hours = int(os.getenv("CRAWL_INTERVAL_HOURS", "24"))
    scheduler = BackgroundScheduler()
    scheduler.add_job(crawl_dynamic_sources, "interval", hours=interval_hours)
    scheduler.start()
    logger.info("[Scheduler] dynamic crawl every %d hours", interval_hours)
    return scheduler
