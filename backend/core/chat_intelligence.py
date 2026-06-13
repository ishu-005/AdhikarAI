"""Small deterministic helpers for chat titles, follow-up rewriting, and query planning."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

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
    clarification_state: dict = field(default_factory=dict)

    def diagnostics(self) -> dict:
        return {
            "query_type": self.query_type,
            "needs_retrieval": self.needs_retrieval,
            "rewritten": self.rewritten,
            "reason": self.reason,
            "issues": list(self.issues),
            "domain_hint": self.domain_hint,
            "clarification_state": self.clarification_state,
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
    "threaten",
    "threatening",
    "threatning",
    "intimidation",
    "violence",
    "domestic",
    "cruelty",
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
    r"husband|wife|threat|threaten|threatening|threatning|intimidation|"
    r"domestic|violence|dowry|harassment|cruelty|"
    r"rti|property|registration|court|complaint|lawyer|rights"
    r")\b",
    re.IGNORECASE,
)

_CLARIFICATION_TOPICS = {
    "disability": ("disability_discrimination", "Disability discrimination by authority"),
    "caste": ("caste_discrimination", "Caste discrimination by authority"),
    "gender": ("gender_discrimination", "Gender discrimination by authority"),
    "religion": ("religious_discrimination", "Religious discrimination by authority"),
    "police/government abuse": ("authority_abuse", "Police or government abuse by authority"),
    "other": ("discrimination", "Discrimination by authority"),
}


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

    awaiting_details = _latest_clarification_details_state(history)
    if awaiting_details and not _is_new_topic(original, awaiting_details):
        effective = f"{awaiting_details['topic']}. {original}"
        return QueryPlan(
            question=effective,
            original_question=original,
            query_type="followup",
            needs_retrieval=True,
            rewritten=True,
            reason="clarification_details",
            issues=split_legal_issues(effective)[:1],
            domain_hint=str(awaiting_details.get("domain") or "human_rights"),
            clarification_state={**awaiting_details, "awaiting_details": False},
        )

    pending = _latest_pending_clarification(history)
    if pending:
        resolved = _resolve_clarification(original, pending)
        if resolved:
            if resolved["choice_only"]:
                return QueryPlan(
                    question=resolved["topic"],
                    original_question=original,
                    query_type="clarification_ack",
                    needs_retrieval=False,
                    rewritten=True,
                    reason="clarification_choice",
                    issues=(),
                    domain_hint=resolved["domain"],
                    clarification_state={k: v for k, v in resolved.items() if k != "choice_only"},
                )
            effective = f"{resolved['topic']}. {original}"
            return QueryPlan(
                question=effective,
                original_question=original,
                query_type="followup",
                needs_retrieval=True,
                rewritten=True,
                reason="clarification_resolved",
                issues=split_legal_issues(effective)[:1],
                domain_hint=resolved["domain"],
                clarification_state={k: v for k, v in resolved.items() if k != "choice_only"},
            )

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


def _latest_pending_clarification(history: list[dict] | None) -> dict | None:
    items = list(history or [])
    for index in range(len(items) - 1, -1, -1):
        item = items[index]
        if item.get("role") != "assistant":
            continue
        diagnostics = (item.get("meta") or {}).get("diagnostics") or {}
        state = diagnostics.get("clarification_state") or {}
        if state.get("awaiting_details"):
            return None
        intent = diagnostics.get("query_intent") or {}
        if not intent.get("needs_clarification"):
            continue
        base_question = ""
        for previous in range(index - 1, -1, -1):
            if items[previous].get("role") == "user":
                base_question = str(items[previous].get("content") or "").strip()
                break
        return {
            "domain": str(intent.get("domain") or "human_rights"),
            "base_question": base_question,
            "choices": tuple(str(choice) for choice in intent.get("clarification_choices") or ()),
        }
    return None


def _latest_clarification_details_state(history: list[dict] | None) -> dict | None:
    for item in reversed(history or []):
        if item.get("role") != "assistant":
            continue
        diagnostics = (item.get("meta") or {}).get("diagnostics") or {}
        state = diagnostics.get("clarification_state") or {}
        if state.get("awaiting_details"):
            label = str(state.get("label") or "Other")
            intent, topic = _topic_for_clarification_label(label)
            return {
                **state,
                "intent": state.get("intent") or intent,
                "topic": state.get("topic") or topic,
            }
        if diagnostics.get("query_intent", {}).get("needs_clarification"):
            return None
    return None


def _resolve_clarification(question: str, pending: dict) -> dict | None:
    raw = _normalize(question)
    choices = list(pending.get("choices") or ())
    selected = ""
    if raw.isdigit():
        index = int(raw) - 1
        if 0 <= index < len(choices):
            selected = choices[index]
    if not selected:
        for choice in choices:
            key = _normalize(choice)
            if raw == key or raw.startswith(f"{key} ") or key.startswith(raw):
                selected = choice
                break
    if not selected and "caste" in raw:
        selected = "Caste"
    if not selected:
        return None

    intent, topic = _topic_for_clarification_label(selected)
    choice_only = len(raw.split()) <= 3
    return {
        "domain": str(pending.get("domain") or "human_rights"),
        "intent": intent,
        "label": selected,
        "topic": topic,
        "base_question": str(pending.get("base_question") or ""),
        "awaiting_details": choice_only,
        "choice_only": choice_only,
    }


def _topic_for_clarification_label(label: str) -> tuple[str, str]:
    topic_key = _normalize(label)
    return _CLARIFICATION_TOPICS.get(topic_key, ("discrimination", f"{label} discrimination by authority"))


def _is_new_topic(question: str, clarification_state: dict) -> bool:
    new_domain, _ = detect_domain(question)
    previous_domain = str(clarification_state.get("domain") or "general")
    if new_domain != "general" and new_domain != previous_domain:
        return True

    text = _normalize(question)
    previous_intent = str(clarification_state.get("intent") or "")
    if previous_domain == "human_rights" and "discrimination" in previous_intent:
        discrimination_terms = (
            "discrimination",
            "authority",
            "benefit",
            "favor",
            "favour",
            "religion",
            "religious",
            "caste",
            "gender",
            "minority",
            "rights",
        )
        if _has_legal_signal(text) and not any(term in text for term in discrimination_terms):
            return True
    return False


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
    if re.search(r"marriage|divorce|dowry|domestic|women|family|husband|wife|threat|cruelty", text):
        return "Family Law Guidance"

    cleaned = re.sub(r"[^\w\s]", "", question, flags=re.UNICODE).strip()
    words = re.sub(r"\s+", " ", cleaned).split()[:5]
    return " ".join(word[:1].upper() + word[1:] for word in words) or "New Legal Chat"
