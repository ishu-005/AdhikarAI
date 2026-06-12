"""Offline RAG evaluation harness.

Measures, over eval/golden.yaml:
  - domain routing accuracy (keyword router vs. expected_domain)
  - retrieval hit-rate (did any retrieved chunk contain a `must_include` term?)
  - answer coverage (did the generated answer contain the `must_include` terms?)
  - language correctness (reply matched expected language)

Writes eval/report.json. Run:  python -m eval.run_eval  (or)  python eval/run_eval.py
Requires the same .env (Supabase + Groq) the app uses.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import yaml

from backend.core.config import resolve_path
from backend.core.text import detect_domain
from backend.rag.pipeline import answer_query
from backend.rag.retriever import retrieve

GOLDEN = Path(__file__).with_name("golden.yaml")
REPORT = resolve_path("eval", "report.json")


def _has_devanagari(text: str) -> bool:
    return bool(re.search(r"[ऀ-ॿ]", text))


def _contains_all(text: str, terms: list[str]) -> bool:
    low = text.lower()
    return all(t.lower() in low for t in terms)


def _contains_any(text: str, terms: list[str]) -> bool:
    low = text.lower()
    return any(t.lower() in low for t in terms)


def main() -> None:
    cases = yaml.safe_load(GOLDEN.read_text(encoding="utf-8"))["questions"]
    rows = []
    agg = {"domain_ok": 0, "retrieval_hit": 0, "answer_cov": 0, "lang_ok": 0}

    for case in cases:
        q = case["q"]
        terms = case.get("must_include", [])
        expected_domain = case.get("expected_domain", "general")
        expected_lang = case.get("lang", "en")

        domain, _ = detect_domain(q)
        domain_ok = domain == expected_domain

        docs = retrieve(q, domain)
        joined = "\n".join(d.page_content for d in docs)
        retrieval_hit = _contains_any(joined, terms) if terms else bool(docs)

        t0 = time.perf_counter()
        result = answer_query(q, domain, expected_lang, history=None)
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        answer = result.get("answer", "")

        answer_cov = _contains_all(answer, terms) if terms else bool(answer)
        if expected_lang == "hi":
            lang_ok = _has_devanagari(answer)
        else:
            lang_ok = not _has_devanagari(answer)

        agg["domain_ok"] += domain_ok
        agg["retrieval_hit"] += retrieval_hit
        agg["answer_cov"] += answer_cov
        agg["lang_ok"] += lang_ok

        rows.append(
            {
                "q": q,
                "domain": domain,
                "expected_domain": expected_domain,
                "domain_ok": domain_ok,
                "n_docs": len(docs),
                "retrieval_hit": retrieval_hit,
                "answer_cov": answer_cov,
                "lang_ok": lang_ok,
                "latency_ms": latency_ms,
            }
        )
        print(
            f"[{'OK ' if domain_ok else 'BAD'}] {q[:48]:48s} "
            f"domain={domain:14s} docs={len(docs)} "
            f"hit={'Y' if retrieval_hit else 'n'} cov={'Y' if answer_cov else 'n'} "
            f"lang={'Y' if lang_ok else 'n'} {latency_ms}ms"
        )

    n = len(cases)
    summary = {k: round(v / n, 3) for k, v in agg.items()}
    print("\n=== Summary ({} cases) ===".format(n))
    for k, v in summary.items():
        print(f"  {k:14s}: {v:.3f}")

    REPORT.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport written to {REPORT}")


if __name__ == "__main__":
    main()
