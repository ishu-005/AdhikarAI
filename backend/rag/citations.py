"""Citation formatting independent of LangChain runtime imports."""
from __future__ import annotations

from typing import Any


def _clean(value: Any) -> str:
    return str(value or "").strip()


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
        content = _content(doc)
        section = _clean(stored.get("section") or md.get("section") or md.get("title") or "Reference")
        source = _clean(stored.get("filename") or md.get("source") or md.get("url") or "Unknown source")
        act_name = _clean(
            stored.get("act_name")
            or stored.get("act")
            or stored.get("document_title")
            or md.get("act_name")
            or md.get("title")
            or stored.get("title")
        )
        title = _clean(md.get("title") or stored.get("title") or act_name)
        url = _clean(stored.get("url") or md.get("url"))
        display = f"{act_name} - {section}" if act_name and section and section != act_name else section
        snippet = " ".join(content.split())[:320]
        context_chunks.append(f"[{i + 1}] {content}")
        citations.append(
            {
                "id": i + 1,
                "section": section,
                "source": source,
                "title": title,
                "act_name": act_name,
                "display": display,
                "domain": md.get("domain", "unknown"),
                "score": round(float(sim), 3) if isinstance(sim, (int, float)) else None,
                "chunk_index": stored.get("chunk_index"),
                "url": url,
                "snippet": snippet,
            }
        )
    return context_chunks, citations
