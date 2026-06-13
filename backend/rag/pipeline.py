"""Orchestration: retrieve -> build context -> generate (sync or streaming).

Returns the same response shape the old `/api/query` produced, so existing
clients keep working. `answer_query` is synchronous; `astream_query` yields
answer tokens and finishes with a metadata payload for the UI.
"""
from __future__ import annotations

import re
from typing import AsyncIterator

from backend.core.config import get_settings
from backend.core.chat_intelligence import QueryPlan, plan_query
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


def _assemble(question: str, domain: str, language: str, plan: QueryPlan | None = None) -> dict:
    """Retrieve context + live sources and prepare prompt inputs."""
    issues = list(plan.issues) if plan and plan.query_type == "legal_multi_issue" else []
    if issues:
        docs = []
        issue_blocks = []
        with metrics.timer("retrieve"):
            for issue in issues[:6]:
                issue_domain, _ = detect_domain(issue)
                issue_docs = retrieve(issue, issue_domain or domain)
                if not issue_docs:
                    metrics.incr("retrieval_empty")
                docs.extend(issue_docs)
                issue_blocks.append(
                    {
                        "issue": issue,
                        "domain": issue_domain or domain,
                        "retrieved": len(issue_docs),
                    }
                )
    else:
        with metrics.timer("retrieve"):
            docs = retrieve(question, domain)
        issue_blocks = []
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
        "issue_block": _format_issue_block(issue_blocks),
        "history_block": "",  # filled by caller if history present
    }
    return {
        "docs": docs,
        "issue_blocks": issue_blocks,
        "context_chunks": context_chunks,
        "citations": citations,
        "live_chunks": live_chunks,
        "sources": sources,
        "context_label": context_label,
        "context_notice": notice,
        "prompt_vars": prompt_vars,
        "diagnostics": _diagnostics(plan, docs, issue_blocks),
    }


def _format_issue_block(issue_blocks: list[dict]) -> str:
    if not issue_blocks:
        return ""
    lines = ["Detected separate legal issues:"]
    for index, issue in enumerate(issue_blocks, start=1):
        status = "sources found" if issue["retrieved"] else "no source found"
        lines.append(f"{index}. {issue['issue']} ({issue['domain']}, {status})")
    return "\n".join(lines)


def _diagnostics(plan: QueryPlan | None, docs: list, issue_blocks: list[dict] | None = None) -> dict:
    base = plan.diagnostics() if plan else {}
    base.update(
        {
            "retrieval_count": len(docs),
            "grounded_issue_count": sum(1 for item in issue_blocks or [] if item.get("retrieved", 0) > 0),
        }
    )
    return base


def _chat_only_answer(question: str, language: str) -> str:
    text = question.strip().lower()
    if language == "hi":
        if text in {"hi", "hello", "hey", "namaste", "namaskar"}:
            return "Namaste. Aap apni legal situation bataiye, main use clear next steps mein tod dunga."
        if text in {"how are you", "kaise ho", "kya haal hai"}:
            return "Main ready hoon. Aap apna legal sawaal ya situation bhejiye."
        return (
            "Main AdhikarAI hoon. Main Indian legal rights ke sawalon par retrieved legal sources ke saath madad karta hoon. "
            "Aap police/FIR, salary, consumer refund, RTI, property, ya family-law situation pooch sakte hain."
        )
    if text in {"hi", "hello", "hey"}:
        return "Hi. Tell me the legal situation you want help with, and I will keep the answer grounded."
    if text in {"how are you", "how are you doing"}:
        return "I am ready. Send me the issue you are facing, and I will help break it into clear next steps."
    if text in {"whats up", "what's up", "sup"}:
        return "Ready to help. You can ask about salary, FIR, consumer refund, RTI, property, or family-law issues."
    if text in {"thanks", "thank you", "ok", "okay"}:
        return "Anytime. Send the next situation when you are ready."
    if text in {"or btao", "aur batao", "aur btao", "anything else"}:
        return "You can ask a follow-up, say `retry`, or start a new legal issue."
    if "yourself" in text or "who are you" in text or "what can you do" in text:
        return (
            "I am AdhikarAI, an Indian legal-rights assistant. Ask me a real legal situation and I will use the legal "
            "knowledge base when retrieval is needed."
        )
    return (
        "Share the situation you want to solve. I can help with Indian legal-rights questions and keep the answer grounded."
    )


def _no_retrieval_payload(question: str, language: str, plan: QueryPlan) -> dict:
    return {
        "answer": _chat_only_answer(question, language),
        "context_sources": ["conversation"],
        "context_source_label": "no retrieval",
        "context_notice": "No legal retrieval was needed for this chat turn.",
        "citations": [],
        "live_sources": [],
        "diagnostics": _diagnostics(plan, [], []),
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
        "diagnostics": ctx.get("diagnostics", {}),
    }


def answer_query(
    question: str,
    domain: str,
    language: str,
    history: list[dict] | None = None,
    query_plan: QueryPlan | None = None,
) -> dict:
    query_plan = query_plan or plan_query(question, history, language)
    if not query_plan.needs_retrieval:
        return _no_retrieval_payload(query_plan.question, language, query_plan)
    question = query_plan.question
    domain, language = _normalize_routing(question, domain, language)
    settings = get_settings()
    if not settings.groq_api_key:
        ctx = _assemble(question, domain, language, query_plan)
        return _result_payload(ctx, "Groq API key is not set.")

    ctx = _assemble(question, domain, language, query_plan)
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
    question: str,
    domain: str,
    language: str,
    history: list[dict] | None = None,
    query_plan: QueryPlan | None = None,
) -> AsyncIterator[dict]:
    """Yield {'type': 'token', 'value': ...} chunks, then a final
    {'type': 'done', ...} with citations and live sources."""
    query_plan = query_plan or plan_query(question, history, language)
    if not query_plan.needs_retrieval:
        result = _no_retrieval_payload(query_plan.question, language, query_plan)
        yield {"type": "replace", "value": result["answer"]}
        yield {"type": "done", **result}
        return
    question = query_plan.question
    domain, language = _normalize_routing(question, domain, language)
    settings = get_settings()
    ctx = _assemble(question, domain, language, query_plan)
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
        "diagnostics": ctx.get("diagnostics", {}),
    }
