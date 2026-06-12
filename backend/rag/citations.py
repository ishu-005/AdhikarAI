"""Citation formatting independent of LangChain runtime imports."""
from __future__ import annotations

from typing import Any


def _metadata(doc: Any) -> dict:
    return getattr(doc, "metadata", None) or {}


def _content(doc: Any) -> str:
    return getattr(doc, "page_content", "") or ""


def build_citations(docs: list[Any]) -> tuple[list[str], list[dict]]:
    context_chunks: list[str] = []
    citations: list[dict] = []
    for i, doc in enumerate(docs):
        md = _metadata(doc)
        stored = md.get("metadata") if isinstance(md.get("metadata"), dict) else {}
        sim = md.get("similarity")
        section = stored.get("section") or md.get("section") or md.get("title") or "Reference"
        source = stored.get("filename") or md.get("source") or md.get("url") or "Unknown source"
        context_chunks.append(f"[{i + 1}] {_content(doc)}")
        citations.append(
            {
                "id": i + 1,
                "section": section,
                "source": source,
                "title": md.get("title") or stored.get("title") or "",
                "domain": md.get("domain", "unknown"),
                "score": round(float(sim), 3) if isinstance(sim, (int, float)) else None,
                "chunk_index": stored.get("chunk_index"),
                "url": stored.get("url") or md.get("url") or "",
            }
        )
    return context_chunks, citations
