"""Shared text, language, and domain helpers.

Ported verbatim (behavior-preserving) from the old monolithic `backend/app.py`,
plus the **fix** for the `links.yaml` path: it is now resolved relative to the
backend package instead of the current working directory.
"""
from __future__ import annotations

import re
import unicodedata

import yaml

from backend.core.config import BACKEND_DIR, get_settings
from backend.core.logging import get_logger

logger = get_logger("text")

LINKS_FILE = BACKEND_DIR / "links.yaml"

DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "criminal_law": ["arrest", "police", "fir", "crime", "bail", "ipc", "bns", "criminal"],
    "consumer": ["refund", "defect", "product", "service", "warranty", "consumer"],
    "labour": ["salary", "wage", "employee", "employer", "factory", "labour", "bonus"],
    "rti": ["rti", "information", "public authority", "pio", "appeal"],
    "human_rights": ["rights", "abuse", "custodial", "discrimination", "nhrc"],
    "women_family": ["dowry", "marriage", "divorce", "domestic violence", "posh", "woman", "women"],
    "citizen_rights": ["constitution", "fundamental rights", "freedom", "equality", "citizen"],
    "property_finance": ["property", "registration", "land", "acquisition", "instrument", "stamp"],
    "case_law": ["judgment", "judgement", "court", "supreme court", "case law", "precedent"],
    "legislation": ["amendment", "bill", "act rules", "legislative", "gazette"],
    "grievance": ["grievance", "complaint portal", "public grievance", "pg portal"],
}

DOMAIN_ALIASES: dict[str, str] = {
    "women": "women_family",
    "women_rights": "women_family",
    "case-law": "case_law",
    "laws": "legislation",
}

HINDI_HINTS = {
    "क्या", "कैसे", "कब", "कहां", "कहाँ", "क्यों", "मुझे", "मेरा", "मेरे",
    "कानून", "अधिकार", "पुलिस", "शिकायत", "अरेस्ट", "जमानत", "एफआईआर",
}


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def normalize_domain(domain: str) -> str:
    lowered = normalize_text(domain).lower().replace(" ", "_")
    lowered = re.sub(r"[^a-z0-9_\-]", "", lowered).replace("-", "_")
    return DOMAIN_ALIASES.get(lowered, lowered)


def detect_language(question: str) -> str:
    normalized = normalize_text(question)
    if not normalized:
        return "en"
    if any("DEVANAGARI" in unicodedata.name(ch, "") for ch in normalized):
        return "hi"
    lowered = f" {normalized.lower()} "
    if any(f" {hint.lower()} " in lowered for hint in HINDI_HINTS):
        return "hi"
    return "en"


def detect_domain(question: str) -> tuple[str, dict[str, int]]:
    q = question.lower()
    scores = {domain: sum(1 for w in words if w in q) for domain, words in DOMAIN_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        best = "general"
    return normalize_domain(best), scores


def load_links_config() -> list[dict]:
    if not LINKS_FILE.exists():
        logger.warning("links.yaml not found at %s; dynamic sources disabled.", LINKS_FILE)
        return []
    with LINKS_FILE.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("dynamic_sources", [])


def get_domain_catalog() -> list[str]:
    settings = get_settings()
    domains = set(settings.allowed_domains)
    domains.update(DOMAIN_KEYWORDS.keys())
    for source in load_links_config():
        d = normalize_domain(str(source.get("domain", "")))
        if d:
            domains.add(d)
    return sorted(domains)


def language_instruction(language: str) -> str:
    if language == "hi":
        return (
            "Reply in simple Hindi. If the retrieved context does not directly support the "
            "answer, say source missing for that issue instead of using outside knowledge."
        )
    return (
        "Reply in simple English. If the retrieved context does not directly support the "
        "answer, say source missing for that issue instead of using outside knowledge."
    )


def context_source_label(
    context_chunks: list[str], live_chunks: list[dict]
) -> tuple[list[str], str, str]:
    sources = ["local embedding"] if context_chunks else []
    if live_chunks:
        sources.append("websites")
    if not sources:
        return ["general knowledge"], "general knowledge", "No retrieved context found"
    label = " + ".join(sources)
    return sources, label, f"Using {label}"


def answer_scope_notice(
    language: str, sources: list[str], context_chunks: list[str], live_chunks: list[dict]
) -> str:
    has_context = bool(context_chunks or live_chunks)
    if language == "hi":
        if has_context:
            return f"स्रोत: {' + '.join(sources)}."
        return "मुझे matching context नहीं मिला, इसलिए यह general best-effort उत्तर है."
    if has_context:
        return f"Source: {' + '.join(sources)}."
    return "I could not find matching context, so source-backed legal next steps are unavailable."
