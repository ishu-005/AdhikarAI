"""Download authoritative Indian bare-act PDFs from India Code into pdfs/<domain>/.

Why this exists: India Code `/handle/...` URLs are HTML landing pages, not PDFs.
Earlier download attempts saved that HTML as `.pdf`, poisoning the corpus. This
downloader resolves the real `/bitstream/.../*Eng.pdf` link from the handle page
and validates every file twice before accepting it:

  1. The bitstream filename encodes the official citation (`A1948-11...` = Act 11
     of 1948); it must match the catalog's expected act year/number.
  2. The PDF must parse with PyMuPDF and its first pages must contain the act's
     title keywords.

Anything that fails validation is discarded (never written into pdfs/).

Run:  python -m backend.ingest.download            # download all missing
      python -m backend.ingest.download --force    # re-download everything
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import fitz  # PyMuPDF
import requests
from bs4 import BeautifulSoup

from backend.core.config import resolve_path
from backend.core.logging import get_logger

logger = get_logger("ingest.download")

BASE = "https://www.indiacode.nic.in"
CENTRAL_ACTS_COMMUNITY = "123456789/1362"
PDF_DIR = resolve_path("pdfs")
REPORT_FILE = PDF_DIR / "download_report.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
}

# Each entry: official citation (act_year, act_no) is the ground truth used to
# validate the bitstream filename; `keywords` must appear in the PDF's first pages.
CATALOG: list[dict] = [
    # ── criminal_law ────────────────────────────────────────────────
    {
        "title": "Bharatiya Sakshya Adhiniyam 2023",
        "domain": "criminal_law", "filename": "BSA_2023.pdf",
        "act_year": 2023, "act_no": 47,
        "query": "Bharatiya Sakshya Adhiniyam",
        "keywords": ["sakshya", "evidence"],
    },
    # ── rti ─────────────────────────────────────────────────────────
    {
        "title": "Right to Information Act 2005",
        "domain": "rti", "filename": "RTI_Act_2005.pdf",
        "act_year": 2005, "act_no": 22,
        "query": "Right to Information Act 2005",
        "keywords": ["right to information"],
    },
    # ── labour ──────────────────────────────────────────────────────
    {
        "title": "Minimum Wages Act 1948",
        "domain": "labour", "filename": "Minimum_Wages_Act_1948.pdf",
        "act_year": 1948, "act_no": 11,
        "query": "Minimum Wages Act 1948",
        "keywords": ["minimum wages"],
    },
    {
        "title": "Payment of Wages Act 1936",
        "domain": "labour", "filename": "Payment_of_Wages_Act_1936.pdf",
        "act_year": 1936, "act_no": 4,
        "query": "Payment of Wages Act 1936",
        "keywords": ["payment of wages"],
    },
    {
        "title": "Factories Act 1948",
        "domain": "labour", "filename": "Factories_Act_1948.pdf",
        "act_year": 1948, "act_no": 63,
        "query": "Factories Act 1948",
        "keywords": ["factories"],
    },
    {
        "title": "Maternity Benefit Act 1961",
        "domain": "labour", "filename": "Maternity_Benefit_Act_1961.pdf",
        "act_year": 1961, "act_no": 53,
        "query": "Maternity Benefit Act 1961",
        "keywords": ["maternity benefit"],
    },
    {
        "title": "Payment of Gratuity Act 1972",
        "domain": "labour", "filename": "Payment_of_Gratuity_Act_1972.pdf",
        "act_year": 1972, "act_no": 39,
        "query": "Payment of Gratuity Act 1972",
        "keywords": ["gratuity"],
    },
    # ── women_family ────────────────────────────────────────────────
    {
        "title": "Hindu Marriage Act 1955",
        "domain": "women_family", "filename": "Hindu_Marriage_Act_1955.pdf",
        "act_year": 1955, "act_no": 25,
        "query": "Hindu Marriage Act 1955",
        "keywords": ["hindu marriage"],
        "handle": "123456789/1560",  # verified
    },
    {
        "title": "Dowry Prohibition Act 1961",
        "domain": "women_family", "filename": "Dowry_Prohibition_Act_1961.pdf",
        "act_year": 1961, "act_no": 28,
        "query": "Dowry Prohibition Act 1961",
        "keywords": ["dowry"],
    },
    {
        "title": "Sexual Harassment of Women at Workplace (POSH) Act 2013",
        "domain": "women_family", "filename": "POSH_Act_2013.pdf",
        "act_year": 2013, "act_no": 14,
        "query": "Sexual Harassment of Women at Workplace",
        "keywords": ["sexual harassment", "workplace"],
    },
    {
        "title": "Hindu Succession Act 1956",
        "domain": "women_family", "filename": "Hindu_Succession_Act_1956.pdf",
        "act_year": 1956, "act_no": 30,
        "query": "Hindu Succession Act 1956",
        "keywords": ["hindu succession"],
    },
    # ── property_finance ────────────────────────────────────────────
    {
        "title": "Transfer of Property Act 1882",
        "domain": "property_finance", "filename": "Transfer_of_Property_Act_1882.pdf",
        "act_year": 1882, "act_no": 4,
        "query": "Transfer of Property Act 1882",
        "keywords": ["transfer of property"],
    },
    {
        "title": "Registration Act 1908",
        "domain": "property_finance", "filename": "Registration_Act_1908.pdf",
        "act_year": 1908, "act_no": 16,
        "query": "Registration Act 1908",
        "keywords": ["registration"],
    },
    {
        "title": "Negotiable Instruments Act 1881",
        "domain": "property_finance", "filename": "Negotiable_Instruments_Act_1881.pdf",
        "act_year": 1881, "act_no": 26,
        "query": "Negotiable Instruments Act 1881",
        "keywords": ["negotiable instruments"],
    },
    {
        "title": "Right to Fair Compensation in Land Acquisition Act 2013",
        "domain": "property_finance", "filename": "Land_Acquisition_Act_2013.pdf",
        "act_year": 2013, "act_no": 30,
        "query": "Right to Fair Compensation and Transparency in Land Acquisition",
        "keywords": ["land acquisition", "fair compensation"],
    },
    # ── human_rights ────────────────────────────────────────────────
    {
        "title": "Protection of Human Rights Act 1993",
        "domain": "human_rights", "filename": "Protection_of_Human_Rights_Act_1993.pdf",
        "act_year": 1994, "act_no": 10,  # official citation: Act 10 of 1994
        "query": "Protection of Human Rights Act",
        "keywords": ["human rights"],
    },
    {
        "title": "SC and ST (Prevention of Atrocities) Act 1989",
        "domain": "human_rights", "filename": "SC_ST_Atrocities_Act_1989.pdf",
        "act_year": 1989, "act_no": 33,
        "query": "Scheduled Castes and the Scheduled Tribes Prevention of Atrocities",
        "keywords": ["atrocities", "scheduled castes"],
    },
    {
        "title": "Rights of Persons with Disabilities Act 2016",
        "domain": "human_rights", "filename": "Disability_Rights_Act_2016.pdf",
        "act_year": 2016, "act_no": 49,
        "query": "Rights of Persons with Disabilities Act 2016",
        "keywords": ["persons with disabilities"],
    },
    # ── citizen_rights ──────────────────────────────────────────────
    {
        "title": "Legal Services Authorities Act 1987",
        "domain": "citizen_rights", "filename": "Legal_Services_Authorities_Act_1987.pdf",
        "act_year": 1987, "act_no": 39,
        "query": "Legal Services Authorities Act 1987",
        "keywords": ["legal services"],
    },
]


_session = requests.Session()
_session.headers.update(HEADERS)


def _get(url: str, **kw) -> requests.Response:
    """GET with retry/backoff — NIC servers intermittently drop TLS under load."""
    last_exc: Exception | None = None
    for attempt in range(4):
        try:
            resp = _session.get(url, timeout=40, **kw)
            resp.raise_for_status()
            return resp
        except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as exc:
            last_exc = exc
            wait = 4 * (attempt + 1)
            logger.info("Transient network error (attempt %d), retrying in %ds: %s", attempt + 1, wait, str(exc)[:90])
            time.sleep(wait)
    raise last_exc  # type: ignore[misc]


# Search-result rows: enactment date, act number, title, then a "View..." link
# like /handle/123456789/18634?view_type=search&col=123456789/2505
_RESULT_ROW = re.compile(
    r"\d{1,2}-[A-Za-z]{3}-(\d{4})</td>\s*<td[^>]*>\s*<em>\s*(\d+)\s*</em>\s*</td>.*?"
    r'href="(/handle/123456789/\d+)\?view_type=search&col=(123456789/\d+)"',
    re.DOTALL,
)


def _search_handles(query: str, act_year: int, act_no: int, limit: int = 5) -> list[str]:
    """Search India Code; return handles whose row citation matches, central acts first."""
    try:
        resp = _get(f"{BASE}/simple-search", params={"query": query})
    except Exception as exc:  # noqa: BLE001
        logger.warning("Search failed for %r: %s", query, exc)
        return []

    matched: list[tuple[int, str]] = []  # (priority, handle)
    fallback: list[str] = []
    for m in _RESULT_ROW.finditer(resp.text):
        row_year, row_no, handle, col = int(m.group(1)), int(m.group(2)), m.group(3), m.group(4)
        if row_year == act_year and row_no == act_no:
            matched.append((0 if col == CENTRAL_ACTS_COMMUNITY else 1, handle))
        else:
            fallback.append(handle)

    matched.sort(key=lambda x: x[0])
    ordered: list[str] = []
    for _, h in matched:
        if h not in ordered:
            ordered.append(h)
    # Only if no citation-matched row exists, fall back to other results —
    # the bitstream filename check still guards against wrong acts.
    for h in fallback:
        if h not in ordered:
            ordered.append(h)
    return ordered[:limit]


def _bitstream_links(handle_path: str) -> list[str]:
    """All PDF bitstream links on a handle page (English versions first)."""
    try:
        resp = _get(f"{BASE}{handle_path}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Handle page failed %s: %s", handle_path, exc)
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    # hrefs on India Code pages often carry stray whitespace — strip before use,
    # otherwise the leading space corrupts the hostname when joined with BASE.
    hrefs = [a["href"].strip() for a in soup.find_all("a", href=True)]
    links = [h for h in hrefs if "/bitstream/" in h and h.lower().endswith(".pdf")]
    # Prefer English bitstreams; deprioritize Hindi (`...Hi.pdf`) and guides.
    links = [l for l in links if "userguide" not in l.lower()]
    return sorted(links, key=lambda l: (0 if "eng" in l.lower() else 1 if "hi" not in l.lower() else 2))


def _filename_matches_citation(bitstream_url: str, act_year: int, act_no: int) -> bool | None:
    """True/False if the filename encodes a citation; None if no pattern found."""
    m = re.search(r"[AH](\d{4})-(\d+)", Path(bitstream_url).name)
    if not m:
        return None
    return int(m.group(1)) == act_year and int(m.group(2)) == act_no


def _validate_pdf(data: bytes, keywords: list[str]) -> str | None:
    """Return None if valid, else a rejection reason."""
    if not data.startswith(b"%PDF-"):
        return "not a PDF (HTML or error page)"
    try:
        with fitz.open(stream=data, filetype="pdf") as doc:
            if doc.page_count == 0:
                return "empty PDF"
            text = " ".join(doc[i].get_text() for i in range(min(4, doc.page_count))).lower()
    except Exception as exc:  # noqa: BLE001
        return f"unparseable PDF: {exc}"
    if len(text.strip()) < 200:
        return "no extractable text (likely scanned image)"
    if not any(k.lower() in text for k in keywords):
        return f"title keywords {keywords} not found in first pages"
    return None


def download_act(entry: dict) -> dict:
    """Resolve, download, and validate one act. Returns a report row."""
    target = PDF_DIR / entry["domain"] / entry["filename"]
    row = {"file": f"{entry['domain']}/{entry['filename']}", "title": entry["title"]}

    candidates: list[str] = []
    if entry.get("handle"):
        candidates.append(f"/handle/{entry['handle']}")
    candidates += _search_handles(entry["query"], entry["act_year"], entry["act_no"])

    tried: list[str] = []
    for handle_path in candidates:
        for bitstream in _bitstream_links(handle_path):
            citation_ok = _filename_matches_citation(bitstream, entry["act_year"], entry["act_no"])
            if citation_ok is False:
                continue  # wrong act on this page
            url = bitstream if bitstream.startswith("http") else f"{BASE}{bitstream}"
            tried.append(url)
            try:
                data = _get(url).content
            except Exception as exc:  # noqa: BLE001
                tried[-1] += f" -> {exc}"
                continue
            reason = _validate_pdf(data, entry["keywords"])
            if reason:
                tried[-1] += f" -> {reason}"
                continue
            # When the filename had no citation pattern, the keyword check above
            # is the only guard — accept but note it.
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            row.update(
                status="ok",
                url=url,
                size_bytes=len(data),
                citation_verified=bool(citation_ok),
            )
            logger.info("[OK] %s (%d KB) <- %s", row["file"], len(data) // 1024, url)
            return row
        time.sleep(2.0)  # be polite between handle pages

    row.update(status="failed", tried=tried or ["no candidate handles found"])
    logger.warning("[FAIL] %s — %d attempts", row["file"], len(tried))
    return row


def main(force: bool = False) -> None:
    rows = []
    for entry in CATALOG:
        target = PDF_DIR / entry["domain"] / entry["filename"]
        if target.exists() and not force:
            issue = _validate_pdf(target.read_bytes(), entry["keywords"])
            if issue is None:
                rows.append({"file": f"{entry['domain']}/{entry['filename']}", "title": entry["title"], "status": "kept"})
                logger.info("[KEEP] %s (already valid)", target.name)
                continue
            logger.warning("[REDO] %s is invalid (%s); re-downloading", target.name, issue)
        rows.append(download_act(entry))
        time.sleep(3.0)  # be polite between acts

    ok = sum(1 for r in rows if r["status"] in {"ok", "kept"})
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": {"ok": ok, "failed": len(rows) - ok, "total": len(rows)},
        "results": rows,
    }
    REPORT_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info("Done: %d/%d acts in place. Report: %s", ok, len(rows), REPORT_FILE)


if __name__ == "__main__":
    main(force="--force" in sys.argv)
