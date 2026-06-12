"""Small deterministic helpers for chat titles and follow-up rewriting."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RewriteResult:
    question: str
    rewritten: bool
    reason: str = ""


_RETRY_COMMANDS = {
    "retry",
    "rety",
    "try again",
    "again",
    "regenerate",
    "rerun",
    "redo",
}
_DETAIL_COMMANDS = {
    "explain more",
    "more details",
    "detail",
    "details",
    "elaborate",
}
_HINDI_COMMANDS = {
    "in hindi",
    "hindi",
    "translate hindi",
    "answer in hindi",
}
_AMBIGUOUS_START = re.compile(
    r"^(what if|and if|if they|if he|if she|then what|what about|can they|can i|do i|does it)\b",
    re.IGNORECASE,
)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower()).rstrip(".?!")


def is_interaction_command(value: str) -> bool:
    text = _normalize(value)
    return text in _RETRY_COMMANDS or text in _DETAIL_COMMANDS or text in _HINDI_COMMANDS


def latest_user_question(history: list[dict] | None) -> str:
    for item in reversed(history or []):
        if item.get("role") != "user":
            continue
        content = str(item.get("content", "")).strip()
        if content and not is_interaction_command(content):
            return content
    return ""


def rewrite_followup(question: str, history: list[dict] | None, language: str) -> RewriteResult:
    raw = question.strip()
    command = _normalize(raw)
    previous = latest_user_question(history)
    if not previous:
        return RewriteResult(raw, False)

    if command in _DETAIL_COMMANDS:
        return RewriteResult(
            f"Explain this in more practical detail with clear next steps: {previous}",
            True,
            "detail_command",
        )
    if command in _HINDI_COMMANDS or (language == "hi" and command in _RETRY_COMMANDS):
        return RewriteResult(
            f"Answer this in Hindi with the same legal grounding: {previous}",
            True,
            "hindi_command",
        )
    if command in _RETRY_COMMANDS:
        return RewriteResult(
            f"Please retry and improve the previous answer for this question: {previous}",
            True,
            "retry_command",
        )
    if len(raw.split()) <= 8 and _AMBIGUOUS_START.search(raw):
        return RewriteResult(
            f"Previous question: {previous}\nFollow-up: {raw}\nAnswer the follow-up in that context.",
            True,
            "ambiguous_followup",
        )
    return RewriteResult(raw, False)


def make_chat_title(question: str) -> str:
    text = _normalize(question)
    if re.search(r"\brti\b|right to information|information application", text):
        return "RTI Filing Help"
    if re.search(r"police|arrest|custody|fir", text):
        return "Police Arrest Rights"
    if re.search(r"refund|defective|consumer|shop|seller|product", text):
        return "Consumer Refund Issue"
    if re.search(r"salary|employer|wage|labour|labor|job", text):
        return "Salary And Labour Rights"
    if re.search(r"murder|bns|bharatiya nyaya|criminal|punishment", text):
        return "Criminal Law Question"
    if re.search(r"registration|property|land|document|deed", text):
        return "Property Registration"
    if re.search(r"marriage|divorce|dowry|domestic|women|family", text):
        return "Family Law Guidance"

    cleaned = re.sub(r"[^\w\s]", "", question, flags=re.UNICODE).strip()
    words = re.sub(r"\s+", " ", cleaned).split()[:5]
    return " ".join(word[:1].upper() + word[1:] for word in words) or "New Legal Chat"
