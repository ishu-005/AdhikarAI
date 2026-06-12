"""Single, process-wide Supabase client.

Replaces the two competing `get_supabase_client()` definitions that used to
live in `backend/app.py`. Returns ``None`` when Supabase is disabled or
unconfigured so callers can degrade gracefully.
"""
from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from backend.core.config import get_settings
from backend.core.logging import get_logger

logger = get_logger("clients")


@lru_cache
def get_supabase_client() -> Client | None:
    settings = get_settings()
    if not settings.use_supabase or not settings.supabase_url or not settings.supabase_api_key:
        logger.info("Supabase disabled or unconfigured; running without a vector store.")
        return None
    try:
        client = create_client(settings.supabase_url, settings.supabase_api_key)
        logger.info("Supabase client initialized.")
        return client
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to initialize Supabase (%s); continuing without it.", exc)
        return None


def reset_supabase_client() -> None:
    """Clear the cached client (useful for tests / config reloads)."""
    get_supabase_client.cache_clear()
