"""Small deterministic helpers for chat titles, follow-up rewriting, and query planning."""
from __future__ import annotations

import re
from dataclasses import dataclass

from backend.core.text import DOMAIN_KEYWORDS, detect_domain


@dataclass(frozen=True)
class RewriteResult:
    question: str
    rewritten: bool
    reason: str = ""


@dataclass(frozen=True)
class QueryPlan:
    question: str
    original_question: str
    query_type: str
    needs_retrieval: bool
    rewritten: bool = False
    reason: str = ""
    issues: tuple[str, ...] = ()
    domain_hint: str = "general"

    def diagnostics(self) -> dict:
        return {
            "query_type": self.query_type,
            "needs_retrieval": self.needs_retrieval,
            "rewritten": self.rewritten,
            "reason": self.reason,
            "issues": list(self.issues),
            "domain_hint": self.domain_hint,
        }


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
_SMALLTALK = {
    "hi",
    "hello",
    "hey",
    "thanks",
    "thank you",
    "ok",
    "okay",
    "or btao",
    "aur batao",
    "aur btao",
    "anything else",
    "tell me about yourself",
    "who are you",
    "what can you do",
}
_AMBIGUOUS_START = re.compile(
    r"^(what if|and if|if they|if he|if she|then what|what about|can they|can i|do i|does it)\b",
    re.IGNORECASE,
)
_LEGAL_EXTRA = {
    "landlord",
    "tenant",
    "rent",
    "security deposit",
    "deposit",
    "husband",
    "wife",
    "threat",
    "threatening",
    "violence",
    "domestic",
    "lawyer",
    "court",
    "complaint",
    "legal",
    "rights",
}
_ISSUE_HINT = re.compile(
    r"\b("
    r"salary|wage|employer|employee|labou?r|landlord|tenant|security deposit|rent|"
    r"defective|refund|consumer|product|warranty|police|fir|arrest|bail|"
    r"husband|wife|threat|threatening|domestic|violence|dowry|harassment|"
    r"rti|property|registration|court|complaint|lawyer|rights"
    r")\b",
    re.IGNORECASE,
)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower()).rstrip(".?!")


def is_interaction_command(value: str) -> bool:
    text = _normalize(value)
    return text in _RETRY_COMMANDS or text in _DETAIL_COMMANDS or text in _HINDI_COMMANDS


def _has_legal_signal(value: str) -> bool:
    text = _normalize(value)
    if _ISSUE_HINT.search(text):
        return True
    return any(keyword in text for words in DOMAIN_KEYWORDS.values() for keyword in words) or any(
        keyword in text for keyword in _LEGAL_EXTRA
    )


def _is_smalltalk(value: str) -> bool:
    text = _normalize(value)
    return text in _SMALLTALK or (
        len(text.split()) <= 4 and not is_interaction_command(text) and not _has_legal_signal(text)
    )


def split_legal_issues(question: str) -> tuple[str, ...]:
    """Split one user message into legal issues without inventing new claims."""
    raw = re.sub(r"\s+", " ", question.strip())
    if not raw:
        return ()

    candidates = re.split(r"(?<=[.!?])\s+|[;\n]+", raw)
    issues: list[str] = []
    for part in candidates:
        cleaned = part.strip(" ,")
        if not cleaned:
            continue
        if _ISSUE_HINT.search(cleaned):
            issues.append(cleaned if cleaned.endswith((".", "?", "!")) else f"{cleaned}.")

    if len(issues) <= 1 and raw.count(",") >= 2:
        for part in re.split(r",|\band\b", raw, flags=re.IGNORECASE):
            cleaned = part.strip(" .")
            if cleaned and _ISSUE_HINT.search(cleaned):
                issues.append(f"{cleaned}.")

    deduped: list[str] = []
    seen: set[str] = set()
    for issue in issues:
        key = _normalize(issue)
        if key not in seen:
            seen.add(key)
            deduped.append(issue)
    return tuple(deduped)


def plan_query(question: str, history: list[dict] | None, language: str) -> QueryPlan:
    """Classify a chat turn before retrieval so RAG is used only when useful."""
    original = question.strip()
    rewrite = rewrite_followup(original, history, language)
    effective = rewrite.question.strip()
    domain, _ = detect_domain(effective)

    if rewrite.rewritten and _has_legal_signal(effective):
        issues = split_legal_issues(effective)
        return QueryPlan(
            question=effective,
            original_question=original,
            query_type="followup",
            needs_retrieval=True,
            rewritten=True,
            reason=rewrite.reason,
            issues=issues[:1],
            domain_hint=domain,
        )

    if _is_smalltalk(effective):
        return QueryPlan(
            question=effective,
            original_question=original,
            query_type="smalltalk",
            needs_retrieval=False,
            rewritten=rewrite.rewritten,
            reason="smalltalk_or_non_legal",
            domain_hint="general",
        )

    if not _has_legal_signal(effective):
        return QueryPlan(
            question=effective,
            original_question=original,
            query_type="smalltalk",
            needs_retrieval=False,
            rewritten=rewrite.rewritten,
            reason="no_legal_signal",
            domain_hint="general",
        )

    issues = split_legal_issues(effective)
    if len(issues) > 1:
        return QueryPlan(
            question=effective,
            original_question=original,
            query_type="legal_multi_issue",
            needs_retrieval=True,
            rewritten=rewrite.rewritten,
            reason="multiple_legal_issues",
            issues=issues,
            domain_hint=domain,
        )

    return QueryPlan(
        question=effective,
        original_question=original,
        query_type="legal_single",
        needs_retrieval=True,
        rewritten=rewrite.rewritten,
        reason=rewrite.reason or "legal_signal",
        issues=issues,
        domain_hint=domain,
    )


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
