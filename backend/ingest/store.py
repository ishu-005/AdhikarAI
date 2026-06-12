"""Embed chunks and upsert them into the Supabase `legal_documents` table.

Uses the same embeddings object as the query path (`backend.rag.embeddings`) so
ingest and retrieval stay dimensionally consistent.

Cloud embedding providers (Cohere trial keys especially) cap throughput at
~100k tokens/min. Bulk ingest is throttled with a sliding-window token budget so
large acts are never dropped to a 429.
"""
from __future__ import annotations

import os
import time
from collections import deque
from datetime import UTC, datetime

from backend.core.clients import get_supabase_client
from backend.core.config import get_settings
from backend.core.logging import get_logger
from backend.rag.embeddings import get_embeddings, normalize_embedding

logger = get_logger("ingest.store")

# ── Rate-limit pacing (one-time bulk ingest; query path is unaffected) ──────
_TOKENS_PER_MIN = int(os.getenv("EMBED_TOKENS_PER_MIN", "80000"))  # safety margin under 100k
_EMBED_BATCH = int(os.getenv("EMBED_BATCH_SIZE", "64"))
_window: deque[tuple[float, int]] = deque()  # (timestamp, tokens)


def _estimate_tokens(texts: list[str]) -> int:
    return max(1, sum(len(t) for t in texts) // 4)


def _throttle(tokens: int) -> None:
    """Block until sending `tokens` keeps us under the per-minute budget."""
    now = time.monotonic()
    while _window and now - _window[0][0] > 60:
        _window.popleft()
    used = sum(t for _, t in _window)
    if _window and used + tokens > _TOKENS_PER_MIN:
        sleep_for = max(1.0, 60 - (now - _window[0][0]) + 0.5)
        logger.info("Embed pacing: sleeping %.1fs (%d tok used in last min)", sleep_for, used)
        time.sleep(sleep_for)
        _window.clear()
    _window.append((time.monotonic(), tokens))


def _embed_with_retry(batch: list[str], attempts: int = 5) -> list[list[float]]:
    """Embed a batch, retrying on transient/rate-limit errors with backoff."""
    delay = 5.0
    for attempt in range(1, attempts + 1):
        try:
            return get_embeddings().embed_documents(batch)
        except Exception as exc:  # noqa: BLE001
            if attempt == attempts:
                raise
            logger.warning("Embed batch failed (attempt %d/%d): %s; backing off %.0fs",
                           attempt, attempts, str(exc)[:120], delay)
            time.sleep(delay)
            delay = min(delay * 2, 60)
    return []  # unreachable


def delete_documents_for_filename(filename: str) -> None:
    """Remove previously ingested chunks of a PDF so re-ingestion never duplicates."""
    client = get_supabase_client()
    if client is None or not filename:
        return
    try:
        client.table("legal_documents").delete().eq("metadata->>filename", filename).execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not delete stale chunks for %s: %s", filename, exc)


def embed_and_store(chunks: list[str], metadatas: list[dict]) -> int:
    if not chunks:
        logger.info("No chunks to store.")
        return 0
    if len(chunks) != len(metadatas):
        raise ValueError("chunks and metadatas must have the same length")

    client = get_supabase_client()
    if client is None:
        logger.error("Supabase client not configured; cannot store documents.")
        return 0

    dim = get_settings().embedding_dimension
    stored = 0

    # Embed + store in rate-paced batches so one big act can't trip a 429.
    for start in range(0, len(chunks), _EMBED_BATCH):
        batch_chunks = chunks[start : start + _EMBED_BATCH]
        batch_metas = metadatas[start : start + _EMBED_BATCH]
        _throttle(_estimate_tokens(batch_chunks))
        vectors = _embed_with_retry(batch_chunks)

        records = []
        for offset, (chunk, meta, vector) in enumerate(zip(batch_chunks, batch_metas, vectors), start=start):
            title = (
                meta.get("title") or meta.get("filename") or meta.get("label")
                or meta.get("section") or "Document"
            )
            records.append(
                {
                    "content": chunk,
                    "domain": meta.get("domain", "general"),
                    "title": title,
                    "source": meta.get("source", "ingested"),
                    "url": meta.get("url"),
                    "embedding": normalize_embedding(list(vector), dim),
                    "metadata": {
                        "filename": meta.get("filename", ""),
                        "section": meta.get("section", ""),
                    "url": meta.get("url", ""),
                    "title": title,
                    "ingested_at": meta.get("ingested_at", datetime.now(UTC).isoformat()),
                    "chunk_index": offset,
                },
            }
            )
        client.table("legal_documents").insert(records).execute()
        stored += len(records)
        logger.info("Stored %d documents in Supabase (%d total).", len(records), stored)

    return stored
