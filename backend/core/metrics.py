"""Lightweight in-process metrics for /api/metrics.

Not a replacement for a real metrics backend — just enough to observe latency
percentiles, cache hit-rate, and per-stage timings during development.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from contextlib import contextmanager
from threading import Lock

_MAX_SAMPLES = 500


class Metrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: dict[str, int] = defaultdict(int)
        self._timers: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=_MAX_SAMPLES))
        self._last_model: str | None = None

    def incr(self, name: str, by: int = 1) -> None:
        with self._lock:
            self._counters[name] += by

    def observe(self, name: str, seconds: float) -> None:
        with self._lock:
            self._timers[name].append(seconds)

    def set_model(self, model: str) -> None:
        with self._lock:
            self._last_model = model

    @contextmanager
    def timer(self, name: str):
        start = time.perf_counter()
        try:
            yield
        finally:
            self.observe(name, time.perf_counter() - start)

    @staticmethod
    def _percentile(values: list[float], pct: float) -> float:
        if not values:
            return 0.0
        values = sorted(values)
        idx = min(len(values) - 1, int(round((pct / 100.0) * (len(values) - 1))))
        return round(values[idx] * 1000, 1)  # ms

    def snapshot(self) -> dict:
        with self._lock:
            counters = dict(self._counters)
            timers = {k: list(v) for k, v in self._timers.items()}
            last_model = self._last_model
        queries = counters.get("query_total", 0)
        cache_hits = counters.get("cache_hit", 0)
        latencies = {
            name: {
                "count": len(samples),
                "p50_ms": self._percentile(samples, 50),
                "p95_ms": self._percentile(samples, 95),
            }
            for name, samples in timers.items()
        }
        return {
            "counters": counters,
            "cache_hit_rate": round(cache_hits / queries, 3) if queries else 0.0,
            "last_model": last_model,
            "latency": latencies,
        }


metrics = Metrics()
