"""Orchestration: retrieve -> build context -> generate (sync or streaming).

Returns the same response shape the old `/api/query` produced, so existing
clients keep working. `answer_query` is synchronous; `astream_query` yields
answer tokens and finishes with a metadata payload for the UI.
"""
from __future__ import annotations

import re
from typing import AsyncIterator

from backend.core.config import get_settings
from backend.core.logging import get_logger
from backend.core.metrics import metrics
from backend.core.text import (
    answer_scope_notice,
    context_source_label,
    detect_domain,
    detect_language,
    language_instruction,
)
from backend.core.web import live_fetch_for_domain
from backend.rag.chain import build_answer_chain
from backend.rag.citations import build_citations
from backend.rag.prompts import fallback_answer, format_docs, format_history, format_live
from backend.rag.retriever import retrieve

logger = get_logger("pipeline")


def _normalize_routing(question: str, domain: str | None, language: str | None) -> tuple[str, str]:
    """Guarantee a non-empty domain/language so retrieval never gets None.

    The route layer normally pre-detects these, but callers (tests, SDK users)
    may omit them; without this guard a None domain crashes retrieval and the
    answer silently falls back to ungrounded LLM general knowledge.
    """
    if not domain:
        domain, _ = detect_domain(question)
    if language not in {"en", "hi"}:
        language = detect_language(question)
    return domain or "general", language


def _assemble(question: str, domain: str, language: str) -> dict:
    """Retrieve context + live sources and prepare prompt inputs."""
    with metrics.timer("retrieve"):
        docs = retrieve(question, domain)
    if not docs:
        metrics.incr("retrieval_empty")
    live_chunks = live_fetch_for_domain(domain) if domain != "general" else []

    context_chunks, citations = build_citations(docs)
    sources, context_label, _ = context_source_label(context_chunks, live_chunks)
    notice = answer_scope_notice(language, sources, context_chunks, live_chunks)

    prompt_vars = {
        "lang_inst": language_instruction(language),
        "question": question,
        "context": format_docs(docs),
        "context_notice": context_label,
        "live_block": format_live(live_chunks),
        "history_block": "",  # filled by caller if history present
    }
    return {
        "docs": docs,
        "context_chunks": context_chunks,
        "citations": citations,
        "live_chunks": live_chunks,
        "sources": sources,
        "context_label": context_label,
        "context_notice": notice,
        "prompt_vars": prompt_vars,
    }


def _hindi_guard(answer: str, language: str, ctx: dict, question: str) -> str:
    if language == "hi" and not re.search(r"[ऀ-ॿ]", answer):
        guarded = fallback_answer(question, ctx["context_chunks"], ctx["live_chunks"], language, ctx["sources"])
        return guarded + "\n\nनोट: मॉडल ने हिंदी में स्पष्ट उत्तर नहीं दिया, इसलिए हिंदी fallback उत्तर दिया गया है."
    return answer


def _result_payload(ctx: dict, answer: str) -> dict:
    return {
        "answer": answer,
        "context_sources": ctx["sources"],
        "context_source_label": ctx["context_label"],
        "context_notice": ctx["context_notice"],
        "citations": ctx["citations"],
        "live_sources": ctx["live_chunks"],
    }


def answer_query(question: str, domain: str, language: str, history: list[dict] | None = None) -> dict:
    domain, language = _normalize_routing(question, domain, language)
    settings = get_settings()
    if not settings.groq_api_key:
        ctx = _assemble(question, domain, language)
        return _result_payload(ctx, "Groq API key is not set.")

    ctx = _assemble(question, domain, language)
    ctx["prompt_vars"]["history_block"] = format_history(history)
    try:
        with metrics.timer("generate"):
            answer = build_answer_chain().invoke(ctx["prompt_vars"])
    except Exception as exc:  # noqa: BLE001
        logger.exception("Answer generation failed: %s", exc)
        answer = fallback_answer(question, ctx["context_chunks"], ctx["live_chunks"], language, ctx["sources"])
    answer = _hindi_guard(answer, language, ctx, question)
    return _result_payload(ctx, answer)


async def astream_query(
    question: str, domain: str, language: str, history: list[dict] | None = None
) -> AsyncIterator[dict]:
    """Yield {'type': 'token', 'value': ...} chunks, then a final
    {'type': 'done', ...} with citations and live sources."""
    domain, language = _normalize_routing(question, domain, language)
    settings = get_settings()
    ctx = _assemble(question, domain, language)
    ctx["prompt_vars"]["history_block"] = format_history(history)

    if not settings.groq_api_key:
        yield {"type": "token", "value": "Groq API key is not set."}
        yield {"type": "done", "answer": "Groq API key is not set.", **_meta(ctx)}
        return

    collected: list[str] = []
    streamed_devanagari = False
    try:
        async for chunk in build_answer_chain().astream(ctx["prompt_vars"]):
            if not chunk:
                continue
            collected.append(chunk)
            if re.search(r"[ऀ-ॿ]", chunk):
                streamed_devanagari = True
            yield {"type": "token", "value": chunk}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Streaming generation failed: %s", exc)

    answer = "".join(collected).strip()
    # Apply the Hindi guard only if nothing usable streamed in Hindi.
    if language == "hi" and not streamed_devanagari:
        answer = _hindi_guard(answer or " ", language, ctx, question)
        yield {"type": "replace", "value": answer}
    elif not answer:
        answer = fallback_answer(question, ctx["context_chunks"], ctx["live_chunks"], language, ctx["sources"])
        yield {"type": "replace", "value": answer}

    yield {"type": "done", "answer": answer, **_meta(ctx)}


def _meta(ctx: dict) -> dict:
    return {
        "context_sources": ctx["sources"],
        "context_source_label": ctx["context_label"],
        "context_notice": ctx["context_notice"],
        "citations": ctx["citations"],
        "live_sources": ctx["live_chunks"],
    }
