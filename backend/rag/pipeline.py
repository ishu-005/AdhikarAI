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
from backend.rag.domain_profiles import (
    QueryIntent,
    build_domain_retrieval_plan,
    build_support_requirements,
    classify_query_intent,
    dedupe_ranked_documents,
    rank_documents_for_intent,
)
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


def _expand_retrieval_query(question: str, domain: str) -> str:
    """Compatibility helper returning the strongest domain-profile expansion."""
    profile = build_domain_retrieval_plan(question, domain)
    if len(profile.queries) > 1:
        return profile.queries[1].query
    return profile.queries[0].query


def _retrieve_with_profile(question: str, domain: str) -> tuple[list, list[dict], int]:
    profile = build_domain_retrieval_plan(question, domain)
    groups = []
    blocks = []
    for item in profile.queries:
        docs = retrieve(item.query, item.domain, scoped=True)
        if not docs:
            metrics.incr("retrieval_empty")
        groups.append(rank_documents_for_intent(question, item.domain, docs))
        blocks.append(
            {
                "query": item.query,
                "domain": item.domain,
                "aspect": item.aspect,
                "retrieved": len(docs),
            }
        )
    docs = dedupe_ranked_documents(groups, profile.context_limit)
    return rank_documents_for_intent(question, domain, docs), blocks, profile.context_limit


def _doc_score(doc) -> float | None:
    metadata = getattr(doc, "metadata", None) or {}
    score = metadata.get("similarity")
    return float(score) if isinstance(score, (int, float)) else None


def _needs_trusted_web_fallback(docs: list, support_block: str, domain: str) -> bool:
    if domain == "general":
        return False
    if not docs:
        return True
    if _has_support_gap(support_block):
        return True
    scores = [score for doc in docs if (score := _doc_score(doc)) is not None]
    return bool(scores and max(scores) < 0.62)


def _has_support_gap(support_block: str) -> bool:
    text = support_block.lower()
    return (
        "source missing" in text
        or "retrieved sources do not provide further guidance" in text
        or "retrieved legal sources do not provide additional guidance" in text
    )


def _source_confidence(
    docs: list,
    live_chunks: list[dict],
    support_block: str,
    used_web_fallback: bool,
) -> dict:
    scores = [score for doc in docs if (score := _doc_score(doc)) is not None]
    max_score = max(scores) if scores else None
    has_support_gap = _has_support_gap(support_block)
    usable_live = [
        item for item in live_chunks
        if item.get("snippet") and not item.get("fetch_error")
    ]

    if used_web_fallback and usable_live:
        level = "web_fallback"
        label = "Trusted web fallback"
        reason = "Database context was weak or missing, so configured trusted legal web sources were included."
    elif docs and not has_support_gap and (max_score is None or max_score >= 0.78):
        level = "strong"
        label = "Strong source match"
        reason = "Retrieved legal database context appears directly relevant."
    elif docs:
        level = "partial"
        label = "Partial source match"
        reason = "Some legal context was found, but exact procedural support may be incomplete."
    else:
        level = "missing"
        label = "Source missing"
        reason = "No matching legal database context or usable configured web source was found."

    return {
        "level": level,
        "label": label,
        "reason": reason,
        "db_chunks": len(docs),
        "live_sources": len(usable_live),
        "max_score": round(max_score, 3) if max_score is not None else None,
        "used_web_fallback": used_web_fallback,
    }


def _assemble(question: str, domain: str, language: str, plan: QueryPlan | None = None) -> dict:
    """Retrieve context + live sources and prepare prompt inputs."""
    issues = list(plan.issues) if plan and plan.query_type == "legal_multi_issue" else []
    retrieval_blocks: list[dict] = []
    context_limit = 5
    if issues:
        docs = []
        issue_blocks = []
        with metrics.timer("retrieve"):
            for issue in issues[:6]:
                issue_domain, _ = detect_domain(issue)
                issue_domain = issue_domain or domain
                issue_docs, issue_retrieval_blocks, issue_context_limit = _retrieve_with_profile(issue, issue_domain)
                if not issue_docs:
                    metrics.incr("retrieval_empty")
                docs.extend(issue_docs)
                retrieval_blocks.extend(issue_retrieval_blocks)
                context_limit = max(context_limit, issue_context_limit)
                issue_blocks.append(
                    {
                        "issue": issue,
                        "domain": issue_domain or domain,
                        "retrieved": len(issue_docs),
                    }
                )
    else:
        with metrics.timer("retrieve"):
            docs, retrieval_blocks, context_limit = _retrieve_with_profile(question, domain)
        issue_blocks = []
    if not docs:
        metrics.incr("retrieval_empty")
    query_intent = classify_query_intent(question, domain)
    support_block = build_support_requirements(question, domain, docs)
    used_web_fallback = _needs_trusted_web_fallback(docs, support_block, domain)
    fallback_terms = [query_intent.intent.replace("_", " ")] + list(query_intent.aspects)
    live_chunks = (
        live_fetch_for_domain(domain, query=question, fallback_terms=fallback_terms)
        if used_web_fallback
        else []
    )

    context_chunks, citations = build_citations(docs)
    sources, context_label, _ = context_source_label(context_chunks, live_chunks)
    notice = answer_scope_notice(language, sources, context_chunks, live_chunks)
    source_confidence = _source_confidence(docs, live_chunks, support_block, used_web_fallback)

    prompt_vars = {
        "lang_inst": language_instruction(language),
        "question": question,
        "context": format_docs(docs, limit=context_limit),
        "context_notice": context_label,
        "support_block": support_block,
        "live_block": format_live(live_chunks),
        "issue_block": _format_issue_block(issue_blocks),
        "history_block": "",  # filled by caller if history present
        "response_format": _response_format(plan),
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
        "diagnostics": _diagnostics(
            plan,
            docs,
            issue_blocks,
            retrieval_blocks,
            query_intent,
            source_confidence,
        ),
    }


def _format_issue_block(issue_blocks: list[dict]) -> str:
    if not issue_blocks:
        return ""
    lines = ["Detected separate legal issues:"]
    for index, issue in enumerate(issue_blocks, start=1):
        status = "sources found" if issue["retrieved"] else "no source found"
        lines.append(f"{index}. {issue['issue']} ({issue['domain']}, {status})")
    return "\n".join(lines)


def _response_format(plan: QueryPlan | None) -> str:
    if plan and plan.answer_style == "educational":
        return (
            "Format the response as:\n"
            "1. Simple explanation: 2-4 short sentences explaining the concept or rights.\n"
            "2. Key points: 4-6 bullets. Cite retrieved support using [1], [2], etc. when available; otherwise say \"The retrieved legal sources do not provide additional guidance on this point.\"\n"
            "3. When this matters: 2-3 practical examples.\n"
            "4. Source note: one short sentence naming any limits in the retrieved context.\n"
            "Do not assume the user already has a dispute, complaint, or violation."
        )
    return (
        "Format the response as:\n"
        "1. Direct answer: 2-3 short sentences.\n"
        "2. What you can do next: 3-5 bullets. Each bullet must either cite retrieved support using [1], [2], etc. or say \"The retrieved legal sources do not provide additional guidance on this point.\"\n"
        "3. Source note: one short sentence naming any limits in the retrieved context."
    )


def _diagnostics(
    plan: QueryPlan | None,
    docs: list,
    issue_blocks: list[dict] | None = None,
    retrieval_blocks: list[dict] | None = None,
    query_intent=None,
    source_confidence: dict | None = None,
) -> dict:
    base = plan.diagnostics() if plan else {}
    base.update(
        {
            "retrieval_count": len(docs),
            "grounded_issue_count": sum(1 for item in issue_blocks or [] if item.get("retrieved", 0) > 0),
            "retrieval_queries": retrieval_blocks or [],
            "query_intent": query_intent.diagnostics() if query_intent else {},
            "source_confidence": source_confidence or {},
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
    if plan.query_type == "clarification_ack":
        label = plan.clarification_state.get("label") or "that type"
        answer = (
            f"Got it: {label}. Share what happened, who the authority was, and what action or denial you faced. "
            "Then I can retrieve the relevant legal material and give grounded next steps."
        )
        return {
            "answer": answer,
            "context_sources": ["clarification"],
            "context_source_label": "clarification",
            "context_notice": "Clarification saved; waiting for the situation details.",
            "citations": [],
            "live_sources": [],
            "diagnostics": _diagnostics(plan, [], []),
        }
    if plan.query_type == "legal_knowledge" and plan.answer_style == "educational":
        return {
            "answer": _curated_knowledge_answer(question, language),
            "context_sources": ["curated knowledge"],
            "context_source_label": "curated knowledge",
            "context_notice": "Educational overview; legal retrieval was not needed for this broad concept question.",
            "citations": [],
            "live_sources": [],
            "diagnostics": _diagnostics(plan, [], []),
        }
    return {
        "answer": _chat_only_answer(question, language),
        "context_sources": ["conversation"],
        "context_source_label": "no retrieval",
        "context_notice": "No legal retrieval was needed for this chat turn.",
        "citations": [],
        "live_sources": [],
        "diagnostics": _diagnostics(plan, [], []),
    }


def _curated_knowledge_answer(question: str, language: str) -> str:
    if language == "hi":
        return (
            "भारत में आपके basic rights में समानता, स्वतंत्रता, शोषण के खिलाफ सुरक्षा, धर्म की स्वतंत्रता, "
            "सांस्कृतिक और शैक्षिक अधिकार, और संवैधानिक उपचार शामिल हैं.\n\n"
            "Key points:\n"
            "- Right to Equality: सरकार या public authority unfair discrimination नहीं कर सकती.\n"
            "- Right to Freedom: speech, movement, association और personal liberty जैसे protections मिलते हैं.\n"
            "- Right against Exploitation: forced labour और exploitation के खिलाफ protection है.\n"
            "- Freedom of Religion: अपनी religion मानने और practice करने की स्वतंत्रता है.\n"
            "- Cultural and Educational Rights: language, culture और education से जुड़े protections हैं.\n"
            "- Constitutional Remedies: rights violate हों तो court में remedy मांग सकते हैं.\n\n"
            "अगर यह किसी specific situation से जुड़ा है, जैसे police, job, landlord, family या consumer issue, तो facts बताइए."
        )
    return (
        "Your basic rights in India include core constitutional protections that limit unfair treatment and abuse of power.\n\n"
        "Key points:\n"
        "- Right to Equality: protection against unfair discrimination by the State.\n"
        "- Right to Freedom: protections for speech, movement, association, and personal liberty.\n"
        "- Right against Exploitation: protection from forced labour and exploitation.\n"
        "- Freedom of Religion: protection to profess, practice, and manage religious affairs within legal limits.\n"
        "- Cultural and Educational Rights: protection for language, culture, and educational interests.\n"
        "- Right to Constitutional Remedies: ability to approach courts when fundamental rights are violated.\n\n"
        "When this matters: discrimination by officials, illegal arrest or detention, speech restrictions, religious discrimination, or misuse of public power.\n\n"
        "If this relates to a specific situation, tell me what happened and I can give more focused guidance."
    )


def _clarification_answer(intent: QueryIntent) -> str:
    choices = "\n".join(f"{index}. {choice}" for index, choice in enumerate(intent.clarification_choices, start=1))
    return f"{intent.clarifying_question}\n\n{choices}"


def _clarification_payload(plan: QueryPlan, intent: QueryIntent) -> dict:
    return {
        "answer": _clarification_answer(intent),
        "context_sources": ["clarification"],
        "context_source_label": "clarification",
        "context_notice": "Clarification is needed before legal retrieval.",
        "citations": [],
        "live_sources": [],
        "diagnostics": _diagnostics(plan, [], [], [], intent),
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
    query_intent = classify_query_intent(question, domain)
    if query_intent.needs_clarification:
        return _clarification_payload(query_plan, query_intent)
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
    query_intent = classify_query_intent(question, domain)
    if query_intent.needs_clarification:
        result = _clarification_payload(query_plan, query_intent)
        yield {"type": "replace", "value": result["answer"]}
        yield {"type": "done", **result}
        return
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
