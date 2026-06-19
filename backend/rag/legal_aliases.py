"""Legal term aliases used to bridge user language and statutory wording."""
from __future__ import annotations

LEGAL_ALIASES: dict[str, tuple[str, ...]] = {
    "fir_filing": (
        "FIR",
        "First Information Report",
        "Zero FIR",
        "information relating to cognizable offence",
        "information in cognizable cases",
        "Section 173 BNSS",
        "officer in charge of a police station",
        "police complaint procedure",
        "oral information",
        "electronic communication",
    ),
    "fir_refusal": (
        "FIR",
        "First Information Report",
        "refusal to register FIR",
        "refusal on the part of an officer in charge",
        "escalation of FIR refusal",
        "Superintendent of Police",
        "Magistrate",
        "Section 173 BNSS",
        "Section 173(4)",
        "Section 175 BNSS",
        "magistrate complaint",
        "police complaint procedure",
    ),
    "arrest_rights": (
        "rights of arrested person",
        "Section 38",
        "Section 47",
        "Section 48",
        "Section 58",
        "Section 53",
        "advocate during interrogation",
        "grounds of arrest",
        "legal practitioner",
        "lawyer",
        "inform relative",
        "family member",
        "24 hours",
        "twenty four hours",
        "produced before Magistrate",
        "medical examination",
    ),
    "religious_discrimination": (
        "religious discrimination",
        "article 25",
        "article 26",
        "freedom of religion",
        "minority rights",
        "constitutional remedy",
    ),
    "caste_discrimination": (
        "caste discrimination",
        "SC/ST",
        "scheduled caste",
        "scheduled tribe",
        "untouchability",
        "article 14",
        "article 15",
        "article 17",
        "SC/ST protections",
        "equality",
        "discrimination",
    ),
    "custodial_violence": (
        "human rights commission",
        "custodial violence",
        "custodial torture",
        "custodial abuse",
        "police custody",
        "police abuse",
        "complaint against police",
        "NHRC complaint",
        "complaint procedure",
        "compensation",
    ),
}

LEGAL_KEYWORD_QUERIES: dict[str, tuple[str, ...]] = {
    "fir_filing": (
        "Section 173 Information in cognizable cases officer in charge police station electronic communication",
        "information relating to the commission of a cognizable offence orally electronic communication",
    ),
    "fir_refusal": (
        "refusal on the part of an officer in charge Superintendent of Police",
        "substance of such information in writing and by post to the Superintendent of Police",
        "Section 173 information in cognizable cases Superintendent of Police",
        "Section 175 BNSS Magistrate complaint police refusal investigation",
    ),
    "arrest_rights": (
        "Section 38 right of arrested person to meet an advocate of his choice during interrogation",
        "Section 47 person arrested informed grounds of arrest right to bail",
        "Section 48 obligation making arrest inform relative friend nominated person",
        "Section 58 person arrested not detained more than twenty four hours Magistrate",
        "Section 53 examination of arrested person by medical officer",
    ),
    "religious_discrimination": (
        "article 25 article 26 freedom of religion minority rights constitutional remedy",
    ),
    "caste_discrimination": (
        "SC/ST protections untouchability article 14 article 15 article 17 equality caste discrimination",
    ),
    "custodial_violence": (
        "human rights commission NHRC complaint custodial violence custodial torture police abuse complaint against police compensation",
    ),
}


def aliases_for(key: str) -> str:
    """Return a compact query suffix for a known legal alias group."""
    return " ".join(LEGAL_ALIASES.get(key, ()))


def keyword_queries_for(key: str) -> tuple[str, ...]:
    """Return focused keyword queries for exact statutory retrieval."""
    return LEGAL_KEYWORD_QUERIES.get(key, ())
