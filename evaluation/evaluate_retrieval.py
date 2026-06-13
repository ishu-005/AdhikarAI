"""Evaluate routing, intent, and optional retrieval quality.

Default mode is offline and deterministic. Use ``--with-retrieval`` only when
Supabase and embeddings are configured and you want to test live chunk recall.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.chat_intelligence import plan_query
from backend.core.text import detect_domain
from backend.rag.domain_profiles import build_domain_retrieval_plan, classify_query_intent
from backend.rag.retriever import retrieve

DEFAULT_CASES = Path(__file__).with_name("test_queries.json")


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _contains_all(actual: list[str], expected: list[str]) -> tuple[int, int]:
    actual_set = set(actual)
    return sum(1 for item in expected if item in actual_set), len(expected)


def _doc_text(doc: Any) -> str:
    metadata = getattr(doc, "metadata", None) or {}
    stored = metadata.get("metadata") if isinstance(metadata.get("metadata"), dict) else {}
    parts = [
        getattr(doc, "page_content", "") or "",
        str(metadata.get("domain", "")),
        str(metadata.get("source", "")),
        str(metadata.get("title", "")),
        str(stored.get("filename", "")),
        str(stored.get("section", "")),
        str(stored.get("title", "")),
    ]
    return " ".join(parts).lower()


def _planned_inspection(query: str, domain: str) -> dict:
    profile = build_domain_retrieval_plan(query, domain)
    return {
        "generated_queries": [
            {"domain": item.domain, "aspect": item.aspect, "query": item.query}
            for item in profile.queries
        ],
        "searched_domains": sorted({item.domain for item in profile.queries}),
        "top_sources": [],
        "top_sections": [],
    }


def _retrieve_case(query: str, domain: str) -> tuple[list[str], list[str], list[str], list[str]]:
    profile = build_domain_retrieval_plan(query, domain)
    domains: list[str] = []
    texts: list[str] = []
    sources: list[str] = []
    sections: list[str] = []
    for item in profile.queries:
        domains.append(item.domain)
        docs = retrieve(item.query, item.domain, scoped=True)
        for doc in docs:
            metadata = getattr(doc, "metadata", None) or {}
            stored = metadata.get("metadata") if isinstance(metadata.get("metadata"), dict) else {}
            texts.append(_doc_text(doc))
            source = str(stored.get("filename") or metadata.get("source") or metadata.get("title") or "")
            section = str(stored.get("section") or metadata.get("section") or metadata.get("title") or "")
            if source:
                sources.append(source)
            if section:
                sections.append(section)
    return sorted(set(domains)), texts, sources[:10], sections[:10]


def evaluate_cases(cases: list[dict], run_retrieval: bool = False) -> dict:
    rows = []
    domain_hits = 0
    intent_hits = 0
    aspect_hits = aspect_total = 0
    secondary_hits = secondary_total = 0
    clarification_hits = clarification_total = 0
    query_term_hits = query_term_total = 0
    retrieval_domain_hits = 0
    source_hits = source_total = 0

    for case in cases:
        query = str(case["query"])
        plan = plan_query(query, [], str(case.get("language", "en")))
        routed_domain = plan.domain_hint if plan.domain_hint != "general" else detect_domain(plan.question)[0]
        intent = classify_query_intent(plan.question, routed_domain)

        expected_domain = str(case.get("expected_domain", ""))
        expected_intent = str(case.get("expected_intent", ""))
        expected_aspects = list(case.get("expected_aspects", []))
        expected_secondary = list(case.get("expected_secondary_domains", []))
        expected_sources = [str(s).lower() for s in case.get("expected_sources", [])]
        expected_query_terms = [str(s).lower() for s in case.get("expected_query_terms", [])]
        expected_needs_clarification = case.get("expected_needs_clarification")

        domain_ok = intent.domain == expected_domain
        intent_ok = not expected_intent or intent.intent == expected_intent
        matched_aspects, total_aspects = _contains_all(list(intent.aspects), expected_aspects)
        matched_secondary, total_secondary = _contains_all(list(intent.secondary_domains), expected_secondary)
        clarification_ok = expected_needs_clarification is None or intent.needs_clarification is bool(expected_needs_clarification)
        if expected_needs_clarification is not None:
            clarification_total += 1
            if clarification_ok:
                clarification_hits += 1

        inspection = _planned_inspection(plan.question, intent.domain)
        planned_query_text = " ".join(item["query"] for item in inspection["generated_queries"]).lower()
        matched_terms = sum(1 for term in expected_query_terms if term in planned_query_text)
        query_term_hits += matched_terms
        query_term_total += len(expected_query_terms)

        retrieved_domains: list[str] = []
        source_ok = None
        if run_retrieval:
            retrieved_domains, retrieved_texts, top_sources, top_sections = _retrieve_case(plan.question, intent.domain)
            inspection["top_sources"] = top_sources
            inspection["top_sections"] = top_sections
            source_ok = all(any(expected in text for text in retrieved_texts) for expected in expected_sources)
            if intent.domain in retrieved_domains:
                retrieval_domain_hits += 1
            if expected_sources:
                source_total += 1
                if source_ok:
                    source_hits += 1

        if domain_ok:
            domain_hits += 1
        if intent_ok:
            intent_hits += 1
        aspect_hits += matched_aspects
        aspect_total += total_aspects
        secondary_hits += matched_secondary
        secondary_total += total_secondary

        rows.append(
            {
                "query": query,
                "expected_domain": expected_domain,
                "predicted_domain": intent.domain,
                "domain_ok": domain_ok,
                "expected_intent": expected_intent,
                "predicted_intent": intent.intent,
                "intent_ok": intent_ok,
                "expected_aspects": expected_aspects,
                "predicted_aspects": list(intent.aspects),
                "expected_secondary_domains": expected_secondary,
                "predicted_secondary_domains": list(intent.secondary_domains),
                "expected_needs_clarification": expected_needs_clarification,
                "needs_clarification": intent.needs_clarification,
                "clarification_ok": clarification_ok,
                "retrieval_inspection": inspection,
                "retrieved_domains": retrieved_domains,
                "source_ok": source_ok,
            }
        )

    total = len(cases)
    result = {
        "total": total,
        "domain_accuracy": _ratio(domain_hits, total),
        "intent_accuracy": _ratio(intent_hits, total),
        "aspect_recall": _ratio(aspect_hits, aspect_total),
        "secondary_domain_recall": _ratio(secondary_hits, secondary_total),
        "clarification_accuracy": _ratio(clarification_hits, clarification_total),
        "query_term_recall": _ratio(query_term_hits, query_term_total),
        "cases": rows,
    }
    if run_retrieval:
        result["retrieval_domain_accuracy"] = _ratio(retrieval_domain_hits, total)
        result["source_recall"] = _ratio(source_hits, source_total)
    return result


def load_cases(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate AdhikarAI retrieval routing and optional live recall.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--with-retrieval", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    result = evaluate_cases(load_cases(args.cases), run_retrieval=args.with_retrieval)
    if args.as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    print(f"Cases: {result['total']}")
    print(f"Domain accuracy: {result['domain_accuracy']:.2%}")
    print(f"Intent accuracy: {result['intent_accuracy']:.2%}")
    print(f"Aspect recall: {result['aspect_recall']:.2%}")
    print(f"Secondary-domain recall: {result['secondary_domain_recall']:.2%}")
    print(f"Clarification accuracy: {result['clarification_accuracy']:.2%}")
    print(f"Query-term recall: {result['query_term_recall']:.2%}")
    if args.with_retrieval:
        print(f"Retrieval-domain accuracy: {result['retrieval_domain_accuracy']:.2%}")
        print(f"Source recall: {result['source_recall']:.2%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
