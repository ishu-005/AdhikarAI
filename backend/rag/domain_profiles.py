"""Domain-aware retrieval planning and context aggregation."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from backend.core.text import normalize_domain


@dataclass(frozen=True)
class RetrievalQuery:
    query: str
    domain: str
    aspect: str


@dataclass(frozen=True)
class DomainRetrievalPlan:
    primary_domain: str
    queries: tuple[RetrievalQuery, ...]
    context_limit: int
    aspects: tuple[str, ...]


@dataclass(frozen=True)
class QueryIntent:
    domain: str
    intent: str
    aspects: tuple[str, ...]
    secondary_domains: tuple[str, ...]
    needs_clarification: bool = False
    clarifying_question: str = ""
    clarification_choices: tuple[str, ...] = ()

    def diagnostics(self) -> dict:
        return {
            "domain": self.domain,
            "intent": self.intent,
            "aspects": list(self.aspects),
            "secondary_domains": list(self.secondary_domains),
            "needs_clarification": self.needs_clarification,
            "clarifying_question": self.clarifying_question,
            "clarification_choices": list(self.clarification_choices),
        }


@dataclass(frozen=True)
class _Aspect:
    name: str
    triggers: tuple[str, ...]
    expansion: str


_PROFILES: dict[str, tuple[_Aspect, ...]] = {
    "women_family": (
        _Aspect(
            "domestic_violence",
            ("husband", "wife", "domestic", "violence", "threat", "threaten", "threatening", "threatning", "cruelty"),
            "domestic violence Protection of Women from Domestic Violence Act protection order residence order protection officer shared household",
        ),
        _Aspect("dowry", ("dowry", "stridhan"), "dowry prohibition demand harassment complaint"),
        _Aspect("marriage", ("marriage", "divorce", "maintenance"), "marriage divorce maintenance matrimonial relief"),
    ),
    "rti": (
        _Aspect("application", ("rti", "application", "information", "pio"), "RTI application public information officer PIO fee"),
        _Aspect("timeline", ("delay", "not replied", "no reply", "time", "days"), "thirty days time limit deemed refusal"),
        _Aspect("appeal", ("appeal", "rejected", "denied", "not replied", "no reply"), "first appeal second appeal information commission"),
        _Aspect("exemption", ("exemption", "refused", "denied"), "exemptions disclosure public interest"),
    ),
    "consumer": (
        _Aspect("defect", ("defect", "defective", "product", "warranty"), "defective goods warranty replacement refund"),
        _Aspect("service", ("service", "deficiency", "delay"), "deficiency in service compensation consumer complaint"),
        _Aspect("complaint", ("refund", "complaint", "seller", "shop"), "consumer commission complaint refund replacement"),
    ),
    "labour": (
        _Aspect("wages", ("salary", "wage", "wages", "payment", "unpaid"), "wages salary non payment employer employee"),
        _Aspect("employment", ("employee", "employer", "job", "termination"), "employment employer employee termination complaint"),
        _Aspect("bonus_factory", ("factory", "bonus", "overtime"), "factory bonus overtime labour authority"),
    ),
    "criminal_law": (
        _Aspect("fir", ("fir", "police", "complaint", "refused"), "FIR police refusal complaint BNSS"),
        _Aspect("arrest_bail", ("arrest", "bail", "custody"), "arrest bail custody rights BNSS"),
        _Aspect("threat", ("threat", "threaten", "threatening", "intimidation"), "criminal intimidation threat alarm injury BNS"),
    ),
    "human_rights": (
        _Aspect("abuse", ("abuse", "custody", "police", "discrimination"), "human rights violation complaint custodial abuse discrimination"),
        _Aspect("disability", ("disability", "disabled"), "rights of persons with disabilities reasonable accommodation complaint"),
        _Aspect("caste", ("caste", "dalit", "sc", "st"), "caste discrimination equality public authority complaint scheduled caste scheduled tribe"),
        _Aspect("gender", ("gender", "woman", "women", "female"), "gender discrimination equality public authority complaint"),
        _Aspect(
            "religion",
            ("religion", "religious", "muslim", "hindu", "christian"),
            (
                "religious discrimination minority rights equality freedom of religion "
                "constitutional remedy public authority commission complaint"
            ),
        ),
    ),
    "property_finance": (
        _Aspect("registration", ("registration", "deed", "instrument", "stamp"), "registration deed instrument stamp registrar"),
        _Aspect("land", ("land", "acquisition", "compensation"), "land acquisition compensation rehabilitation resettlement"),
        _Aspect("tenant", ("landlord", "tenant", "rent", "security deposit"), "landlord tenant rent security deposit lease"),
    ),
    "citizen_rights": (
        _Aspect("constitution", ("constitution", "fundamental", "rights", "freedom", "equality"), "fundamental rights constitution equality freedom remedy"),
        _Aspect("legal_aid", ("legal aid", "lawyer", "free lawyer"), "legal services authority free legal aid eligibility"),
    ),
    "grievance": (
        _Aspect("complaint", ("complaint", "grievance", "portal", "escalate"), "public grievance complaint portal acknowledgement escalation"),
    ),
}

_SECONDARY_RULES: dict[str, tuple[tuple[tuple[str, ...], str, str], ...]] = {
    "women_family": (
        (("threat", "threatening", "threatning", "police", "fir", "violence"), "criminal_law", "criminal intimidation FIR police complaint BNSS BNS"),
    ),
    "criminal_law": (
        (("husband", "wife", "domestic", "dowry"), "women_family", "domestic violence protection order protection officer"),
        (("custody", "abuse", "discrimination"), "human_rights", "human rights complaint custodial abuse"),
    ),
    "rti": (
        (("complaint", "grievance", "portal", "escalate"), "grievance", "public grievance portal complaint escalation"),
    ),
    "labour": (
        (("complaint", "grievance", "portal", "authority"), "grievance", "public grievance labour complaint escalation"),
    ),
    "consumer": (
        (("complaint", "portal", "grievance"), "grievance", "consumer grievance complaint portal escalation"),
    ),
}

_REMEDY_EXPANSIONS: dict[str, str] = {
    "women_family": (
        "procedure complaint application to Magistrate Section 12 domestic incident report "
        "Protection Officer service provider notice hearing"
    ),
    "rti": "procedure RTI application PIO time limit first appeal second appeal information commission",
    "consumer": "procedure consumer complaint consumer commission district commission refund replacement compensation",
    "labour": "procedure labour authority complaint inspector wages claim employer non payment",
    "criminal_law": (
        "procedure FIR procedure police complaint Superintendent of Police magistrate complaint "
        "complaint to Magistrate BNSS refusal to register FIR"
    ),
    "property_finance": "procedure registrar registration refusal appeal deed instrument stamp",
    "human_rights": "procedure human rights complaint commission petition custodial abuse",
    "citizen_rights": "procedure legal aid application legal services authority remedy",
    "grievance": "procedure grievance complaint portal acknowledgement escalation",
}


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    for term in terms:
        if len(term) <= 3:
            if re.search(rf"\b{re.escape(term)}\b", text):
                return True
            continue
        if term in text:
            return True
    return False


def build_domain_retrieval_plan(question: str, domain: str) -> DomainRetrievalPlan:
    primary = normalize_domain(domain) or "general"
    text = question.lower()
    queries: list[RetrievalQuery] = [RetrievalQuery(query=query_with_domain_hint(question, primary), domain=primary, aspect="original")]
    aspects: list[str] = ["original"]

    for aspect in _PROFILES.get(primary, ()):
        if _contains_any(text, aspect.triggers):
            queries.append(RetrievalQuery(f"{question} {aspect.expansion}", primary, aspect.name))
            aspects.append(aspect.name)

    if len(queries) == 1 and primary in _PROFILES:
        default = _PROFILES[primary][0]
        queries.append(RetrievalQuery(f"{question} {default.expansion}", primary, default.name))
        aspects.append(default.name)

    remedy = _REMEDY_EXPANSIONS.get(primary)
    if remedy:
        queries.append(RetrievalQuery(f"{question} {remedy}", primary, "procedure"))
        aspects.append("procedure")

    for triggers, secondary_domain, expansion in _SECONDARY_RULES.get(primary, ()):
        if _contains_any(text, triggers):
            queries.append(RetrievalQuery(f"{question} {expansion}", secondary_domain, f"secondary:{secondary_domain}"))
            aspects.append(f"secondary:{secondary_domain}")

    deduped: list[RetrievalQuery] = []
    seen: set[tuple[str, str]] = set()
    for item in queries:
        key = (item.domain, re.sub(r"\s+", " ", item.query.lower()).strip())
        if key not in seen:
            seen.add(key)
            deduped.append(item)

    if primary == "criminal_law" and any(item.aspect == "fir" for item in deduped):
        priority = {"fir": 0, "procedure": 1, "original": 2}
        deduped.sort(key=lambda item: priority.get(item.aspect, 3))

    context_limit = 7 if len(deduped) > 2 else 5
    return DomainRetrievalPlan(primary, tuple(deduped[:5]), context_limit, tuple(aspects))


def classify_query_intent(question: str, domain: str) -> QueryIntent:
    profile = build_domain_retrieval_plan(question, domain)
    aspects = tuple(a for a in profile.aspects if not a.startswith("secondary:"))
    secondary_domains = tuple(a.split(":", 1)[1] for a in profile.aspects if a.startswith("secondary:"))
    if _needs_discrimination_clarification(question, profile.primary_domain):
        return QueryIntent(
            domain=profile.primary_domain,
            intent="ambiguous_discrimination",
            aspects=aspects,
            secondary_domains=secondary_domains,
            needs_clarification=True,
            clarifying_question="What type of discrimination is this?",
            clarification_choices=(
                "Disability",
                "Caste",
                "Gender",
                "Religion",
                "Police/Government abuse",
                "Other",
            ),
        )
    candidates = [a for a in aspects if a not in {"original", "procedure"}]
    intent = _prefer_intent(profile.primary_domain, candidates) if candidates else (
        aspects[1] if len(aspects) > 1 else "general"
    )
    return QueryIntent(profile.primary_domain, intent, aspects, secondary_domains)


def _needs_discrimination_clarification(question: str, domain: str) -> bool:
    text = question.lower()
    if domain not in {"human_rights", "citizen_rights"} or "discrimination" not in text:
        return False
    specific_markers = (
        "disability",
        "disabled",
        "caste",
        "dalit",
        "sc",
        "st",
        "gender",
        "woman",
        "women",
        "female",
        "religion",
        "religious",
        "muslim",
        "hindu",
        "christian",
        "police",
        "custody",
        "abuse",
    )
    return not any(re.search(rf"\b{re.escape(marker)}\b", text) for marker in specific_markers)


def _prefer_intent(domain: str, candidates: list[str]) -> str:
    priority = {
        "women_family": ("dowry", "domestic_violence", "marriage"),
        "rti": ("appeal", "timeline", "application", "exemption"),
        "consumer": ("complaint", "defect", "service"),
        "labour": ("wages", "employment", "bonus_factory"),
        "criminal_law": ("fir", "threat", "arrest_bail"),
        "property_finance": ("tenant", "registration", "land"),
        "human_rights": ("caste", "disability", "gender", "religion", "abuse"),
        "citizen_rights": ("legal_aid", "constitution"),
        "grievance": ("complaint",),
    }
    for preferred in priority.get(domain, ()):
        if preferred in candidates:
            return preferred
    return candidates[0]


def query_with_domain_hint(question: str, domain: str) -> str:
    if domain == "general":
        return question
    return f"{question} {domain.replace('_', ' ')}"


def _doc_key(doc: Any) -> tuple[str, str, str]:
    metadata = getattr(doc, "metadata", None) or {}
    stored = metadata.get("metadata") if isinstance(metadata.get("metadata"), dict) else {}
    source = str(stored.get("filename") or metadata.get("source") or metadata.get("url") or "")
    title = str(stored.get("title") or metadata.get("title") or "")
    content = re.sub(r"\s+", " ", (getattr(doc, "page_content", "") or "")).strip()[:500]
    return source, title, content


def _doc_text(doc: Any) -> str:
    metadata = getattr(doc, "metadata", None) or {}
    stored = metadata.get("metadata") if isinstance(metadata.get("metadata"), dict) else {}
    return " ".join(
        [
            getattr(doc, "page_content", "") or "",
            str(metadata.get("domain", "")),
            str(metadata.get("source", "")),
            str(metadata.get("title", "")),
            str(stored.get("filename", "")),
            str(stored.get("section", "")),
            str(stored.get("title", "")),
        ]
    ).lower()


def rank_documents_for_intent(question: str, domain: str, docs: list[Any]) -> list[Any]:
    """Apply small deterministic boosts/penalties after retriever ranking."""
    intent = classify_query_intent(question, domain)
    question_text = question.lower()

    def score(index_doc: tuple[int, Any]) -> tuple[int, int]:
        index, doc = index_doc
        text = _doc_text(doc)
        value = 0
        if intent.domain == "criminal_law" and intent.intent == "fir":
            value += _term_score(text, ("fir", "first information report"), 5)
            value += _term_score(text, ("register", "registration", "refusal", "refused"), 3)
            value += _term_score(text, ("superintendent of police", "magistrate", "police complaint"), 5)
            if not _contains_any(question_text, ("witness", "threat", "threaten", "threatening", "intimidation")):
                value -= _term_score(text, ("witness", "false evidence", "threatening any person", "intimidation"), 4)
        elif intent.domain == "human_rights" and intent.intent == "religion":
            value += _term_score(text, ("religion", "religious", "minority", "minorities"), 4)
            value += _term_score(text, ("equality", "freedom of religion", "article 25", "article 26"), 3)
            value += _term_score(text, ("commission", "constitutional remedy", "public authority"), 2)
        return -value, index

    return [doc for _, doc in sorted(enumerate(docs), key=score)]


def _term_score(text: str, terms: tuple[str, ...], weight: int) -> int:
    return sum(weight for term in terms if term in text)


def build_support_requirements(question: str, domain: str, docs: list[Any]) -> str:
    intent = classify_query_intent(question, domain)
    doc_text = " ".join(_doc_text(doc) for doc in docs)
    lines: list[str] = []
    if intent.domain == "criminal_law" and intent.intent == "fir":
        has_fir_escalation = (
            ("superintendent of police" in doc_text or "magistrate" in doc_text)
            and ("fir" in doc_text or "first information report" in doc_text)
        )
        if has_fir_escalation:
            lines.append("FIR escalation procedure appears supported by retrieved context.")
        else:
            lines.append("For FIR escalation procedure, say source missing for exact FIR escalation procedure.")
    if intent.domain == "human_rights" and intent.intent == "religion":
        has_religion_context = any(
            term in doc_text
            for term in ("religious discrimination", "freedom of religion", "minority rights", "minorities")
        )
        if has_religion_context:
            lines.append("Religious discrimination context appears supported by retrieved context.")
        else:
            lines.append("For religious discrimination procedure, say source missing for focused religious-discrimination procedure.")
    if not lines:
        return ""
    return "Support checks:\n" + "\n".join(f"- {line}" for line in lines)


def dedupe_ranked_documents(groups: list[list[Any]], limit: int) -> list[Any]:
    selected: list[Any] = []
    seen: set[tuple[str, str, str]] = set()
    max_len = max((len(group) for group in groups), default=0)

    for index in range(max_len):
        for group in groups:
            if index >= len(group):
                continue
            doc = group[index]
            key = _doc_key(doc)
            if key in seen:
                continue
            seen.add(key)
            selected.append(doc)
            if len(selected) >= limit:
                return selected
    return selected
