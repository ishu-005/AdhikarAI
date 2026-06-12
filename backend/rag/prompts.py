"""Prompt templates and the bilingual best-effort fallback answer."""
from __future__ import annotations

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate

SYSTEM_PROMPT = (
    "You are AdhikarAI, a legal guidance assistant for Indian citizens. "
    "Answer from the supplied legal context first. Be direct, practical, and concise. "
    "If the context is weak, say so briefly instead of guessing. This is general guidance, not legal advice."
)

USER_PROMPT = """{lang_inst}

Give a useful, fact-focused answer based on the material below.

Question: {question}

Context ({context_notice}):
{context}

{live_block}

{history_block}

Format the response as:
1. Direct answer: 2-3 short sentences.
2. What you can do next: 3-5 bullets.
3. Source note: one short sentence naming any limits in the retrieved context.

Keep the answer compact. Do not repeat long disclaimers. General guidance only, not legal advice."""

PROMPT = ChatPromptTemplate.from_messages(
    [("system", SYSTEM_PROMPT), ("user", USER_PROMPT)]
)


def format_docs(docs: list[Document], limit: int = 3) -> str:
    if not docs:
        return "No document sources found."
    return "\n\n".join(f"[{i + 1}] {d.page_content}" for i, d in enumerate(docs[:limit]))


def format_live(live_chunks: list[dict], limit: int = 2) -> str:
    if not live_chunks:
        return ""
    lines = [f"- {x.get('label', 'Source')}: {x.get('snippet', '')[:200]}" for x in live_chunks[:limit]]
    return "Recent updates:\n" + "\n".join(lines)


def format_history(history: list[dict] | None, window: int = 3) -> str:
    items = (history or [])[-window:]
    if not items:
        return ""
    lines = [f"{i.get('role', '').title()}: {i.get('content', '')[:100]}" for i in items]
    return "Previous discussion:\n" + "\n".join(lines)


def fallback_answer(
    question: str,
    context_chunks: list[str],
    live_chunks: list[dict],
    language: str,
    sources: list[str],
) -> str:
    if language == "hi":
        intro = "प्रश्न"
        guidance_title = "सरल जवाब"
        references_title = "संबंधित संदर्भ"
        live_title = "लाइव स्रोत"
        no_context = "मुझे exact context नहीं मिला, इसलिए यह best-effort उत्तर है."
        tips = [
            "पहले तथ्य, तारीखें और सबूत इकट्ठा करें.",
            "सही authority या office में लिखित शिकायत करें.",
            "complaint number, acknowledgement और response की copy रखें.",
        ]
    else:
        intro, guidance_title, references_title, live_title = (
            "Question", "Plain-language guidance", "Relevant references", "Live source snapshot"
        )
        no_context = "I could not find exact matching context, so this is a best-effort answer."
        tips = [
            "Document facts, dates, and proof first.",
            "Use the right authority or office and file in writing if possible.",
            "Keep copies of complaint numbers, acknowledgements, and responses.",
        ]

    brief_context = "\n".join(context_chunks[:3]) if context_chunks else "No matching legal chunk found."
    live_bits = [f"- {i.get('label')}: {i.get('snippet', '')[:220]}..." for i in live_chunks if i.get("snippet")]
    live_text = "\n".join(live_bits) if live_bits else "No live-source update was available."
    note = no_context if not (context_chunks or live_chunks) else "This answer is based on the retrieved context."
    return (
        f"{intro}: {question}\n\n"
        f"{guidance_title}:\n1) {tips[0]}\n2) {tips[1]}\n3) {tips[2]}\n\n"
        f"Context note: {note}\nContext source: {' + '.join(sources)}\n\n"
        f"{references_title}:\n{brief_context}\n\n"
        f"{live_title}:\n{live_text}\n"
    )
