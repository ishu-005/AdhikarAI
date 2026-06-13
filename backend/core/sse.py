"""Server-sent event helpers used by streaming API routes."""
from __future__ import annotations

import json
from collections.abc import Iterator


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def cached_stream_events(conversation_id: str, domain: str, language: str, cached: dict) -> Iterator[str]:
    yield sse(
        "meta",
        {
            "conversation_id": conversation_id,
            "domain": domain,
            "language": language,
            "_cached": True,
            "diagnostics": cached.get("diagnostics", {}),
        },
    )
    yield sse("replace", {"value": cached.get("answer", "")})
    yield sse(
        "done",
        {
            "answer": cached.get("answer", ""),
            "context_sources": cached.get("context_sources", []),
            "context_source_label": cached.get("context_source_label", ""),
            "context_notice": cached.get("context_notice", ""),
            "citations": cached.get("citations", []),
            "live_sources": cached.get("live_sources", []),
            "diagnostics": cached.get("diagnostics", {}),
            "_cached": True,
        },
    )
