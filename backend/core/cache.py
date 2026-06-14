"""In-memory TTL cache for repeated queries (keyed on question|domain|language)."""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from threading import Lock


class OptimizationCache:
    def __init__(self, ttl_seconds: int = 1800) -> None:
        self._cache: dict[str, tuple[dict, datetime]] = {}
        self._ttl = ttl_seconds
        self._lock = Lock()

    @staticmethod
    def _key(question: str, domain: str, language: str, scope: str = "") -> str:
        return hashlib.md5(f"{scope}|{question.lower().strip()}|{domain}|{language}".encode()).hexdigest()

    def get(self, question: str, domain: str, language: str, scope: str = "") -> dict | None:
        key = self._key(question, domain, language, scope)
        with self._lock:
            entry = self._cache.get(key)
            if not entry:
                return None
            value, ts = entry
            if datetime.now(UTC) - ts < timedelta(seconds=self._ttl):
                return value
            del self._cache[key]
        return None

    def set(self, question: str, domain: str, language: str, value: dict, scope: str = "") -> None:
        with self._lock:
            self._cache[self._key(question, domain, language, scope)] = (value, datetime.now(UTC))
