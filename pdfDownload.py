import json
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
import fitz

# Target legal PDFs with resilient candidate sources.
# For each file we try direct URLs first, then scrape candidate pages to discover PDF links.
PDF_TARGETS: dict[str, dict] = {
    "criminal_law/BNS_2023.pdf": {
        "title": "Bharatiya Nyaya Sanhita 2023",
        "candidates": [
            "https://www.mha.gov.in/sites/default/files/250883_english_01042024.pdf",
            "https://www.indiacode.nic.in/handle/123456789/20062",
            "https://lddashboard.legislative.gov.in/",
        ],
    },
    "criminal_law/BNSS_2023.pdf": {
        "title": "Bharatiya Nagarik Suraksha Sanhita 2023",
        "candidates": [
            "https://bprd.nic.in/uploads/pdf/Final_BNSS.pdf",
            "https://www.indiacode.nic.in/handle/123456789/21544",
            "https://lddashboard.legislative.gov.in/",
        ],
    },
    "criminal_law/BSA_2023.pdf": {
        "title": "Bharatiya Sakshya Adhiniyam 2023",
        "candidates": [
            "https://bprd.nic.in/uploads/pdf/BSA.pdf",
            "https://www.indiacode.nic.in/handle/123456789/21202",
            "https://lddashboard.legislative.gov.in/",
        ],
    },
    "citizen_rights/RTI_Act_2005.pdf": {
        "title": "Right to Information Act 2005",
        "candidates": [
            "https://cic.gov.in/sites/default/files/RTI-Act_English.pdf",
            "https://www.indiacode.nic.in/handle/123456789/2064",
            "https://lddashboard.legislative.gov.in/",
        ],
    },
    "citizen_rights/Constitution_of_India.pdf": {
        "title": "Constitution of India",
        "candidates": [
            "https://legislative.gov.in/sites/default/files/COI-updated-as-31072018.pdf",
        ],
    },
    "consumer/Consumer_Protection_Act_2019.pdf": {
        "title": "Consumer Protection Act 2019",
        "candidates": [
            "https://www.indiacode.nic.in/bitstream/123456789/16939/1/a2019-35.pdf",
            "https://www.indiacode.nic.in/handle/123456789/16939",
            "https://lddashboard.legislative.gov.in/",
        ],
    },
    "women_family/Domestic_Violence_Act_2005.pdf": {
        "title": "Protection of Women from Domestic Violence Act 2005",
        "candidates": [
            "https://www.indiacode.nic.in/bitstream/123456789/15436/1/protection_of_women_from_domestic_violence_act,_2005.pdf",
            "https://www.indiacode.nic.in/handle/123456789/15436",
            "https://lddashboard.legislative.gov.in/",
        ],
    },
    "women_family/Dowry_Prohibition_Act_1961.pdf": {
        "title": "Dowry Prohibition Act 1961",
        "candidates": [
            "https://lddashboard.legislative.gov.in/sites/default/files/A1961-28.pdf",
            "https://www.indiacode.nic.in/handle/123456789/1477",
        ],
    },
    "women_family/Hindu_Marriage_Act_1955.pdf": {
        "title": "Hindu Marriage Act 1955",
        "candidates": [
            "https://lddashboard.legislative.gov.in/sites/default/files/The%20Hindu%20Marriage%20Act,%201955%20%2825%20of%201955%29.pdf",
            "https://www.indiacode.nic.in/handle/123456789/1494",
        ],
    },
    "women_family/Special_Marriage_Act_1954.pdf": {
        "title": "Special Marriage Act 1954",
        "candidates": [
            "https://lddashboard.legislative.gov.in/sites/default/files/A1954-43.pdf",
            "https://www.indiacode.nic.in/handle/123456789/1387",
        ],
    },
    "women_family/POSH_Act_2013.pdf": {
        "title": "Sexual Harassment of Women at Workplace Act 2013",
        "candidates": [
            "https://wcd.nic.in/sites/default/files/Sexual%20Harassment%20at%20Workplace%20Act.pdf",
            "https://www.indiacode.nic.in/handle/123456789/15544",
        ],
    },
    "labour/Minimum_Wages_Act_1948.pdf": {
        "title": "Minimum Wages Act 1948",
        "candidates": [
            "https://lddashboard.legislative.gov.in/sites/default/files/A1948-11.pdf",
            "https://www.indiacode.nic.in/handle/123456789/1380",
        ],
    },
    "labour/Payment_of_Wages_Act_1936.pdf": {
        "title": "Payment of Wages Act 1936",
        "candidates": [
            "https://lddashboard.legislative.gov.in/sites/default/files/A1936-4.pdf",
            "https://www.indiacode.nic.in/handle/123456789/1367",
        ],
    },
    "labour/Factories_Act_1948.pdf": {
        "title": "Factories Act 1948",
        "candidates": [
            "https://lddashboard.legislative.gov.in/sites/default/files/A1948-63.pdf",
            "https://www.indiacode.nic.in/handle/123456789/1382",
        ],
    },
    "labour/Maternity_Benefit_Act_1961.pdf": {
        "title": "Maternity Benefit Act 1961",
        "candidates": [
            "https://lddashboard.legislative.gov.in/sites/default/files/A1961-53.pdf",
            "https://www.indiacode.nic.in/handle/123456789/1534",
        ],
    },
    "property_finance/Negotiable_Instruments_Act_1881.pdf": {
        "title": "Negotiable Instruments Act 1881",
        "candidates": [
            "https://lddashboard.legislative.gov.in/sites/default/files/A1881-26.pdf",
            "https://www.indiacode.nic.in/handle/123456789/2311",
        ],
    },
    "property_finance/Transfer_of_Property_Act_1882.pdf": {
        "title": "Transfer of Property Act 1882",
        "candidates": [
            "https://lddashboard.legislative.gov.in/sites/default/files/A1882-4.pdf",
            "https://www.indiacode.nic.in/handle/123456789/2312",
        ],
    },
    "property_finance/Registration_Act_1908.pdf": {
        "title": "Registration Act 1908",
        "candidates": [
            "https://lddashboard.legislative.gov.in/sites/default/files/A1908-16.pdf",
            "https://www.indiacode.nic.in/handle/123456789/2368",
        ],
    },
    "property_finance/Land_Acquisition_Act_2013.pdf": {
        "title": "Land Acquisition Act 2013",
        "candidates": [
            "https://lddashboard.legislative.gov.in/sites/default/files/A2013-30.pdf",
            "https://www.indiacode.nic.in/handle/123456789/2371",
        ],
    },
    "human_rights/Protection_of_Human_Rights_Act_1993.pdf": {
        "title": "Protection of Human Rights Act 1993",
        "candidates": [
            "https://lddashboard.legislative.gov.in/sites/default/files/A1994-10.pdf",
            "https://www.indiacode.nic.in/handle/123456789/1805",
        ],
    },
    "human_rights/SC_ST_Atrocities_Act_1989.pdf": {
        "title": "SC ST Atrocities Act 1989",
        "candidates": [
            "https://lddashboard.legislative.gov.in/sites/default/files/A1989-33.pdf",
            "https://www.indiacode.nic.in/handle/123456789/1652",
        ],
    },
    "human_rights/Disability_Rights_Act_2016.pdf": {
        "title": "Rights of Persons with Disabilities Act 2016",
        "candidates": [
            "https://lddashboard.legislative.gov.in/sites/default/files/A2016-49_0.pdf",
            "https://www.indiacode.nic.in/handle/123456789/11715",
        ],
    },
}

DOWNLOAD_TIMEOUT = int(os.getenv("PDF_DOWNLOAD_TIMEOUT", "40"))
MAX_RETRIES = int(os.getenv("PDF_DOWNLOAD_RETRIES", "3"))
RETRY_BACKOFF_SEC = float(os.getenv("PDF_DOWNLOAD_BACKOFF_SEC", "2"))
ALLOW_INSECURE_SSL = os.getenv("ALLOW_INSECURE_SSL", "false").lower() == "true"

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

TITLE_STOPWORDS = {
    "act",
    "law",
    "code",
    "india",
    "indian",
    "rights",
    "right",
    "persons",
    "person",
    "protection",
    "of",
    "the",
    "and",
    "for",
    "with",
    "from",
    "to",
}


def _norm_tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _title_keywords(title: str) -> set[str]:
    tokens = _norm_tokens(title)
    return {token for token in tokens if token not in TITLE_STOPWORDS and len(token) >= 3}


def validate_pdf_payload(content: bytes, content_type: str | None) -> str | None:
    if not content:
        return "empty response body"

    sniff = content[:1024].lower()
    if sniff.startswith(b"<") or b"<html" in sniff:
        return "response is HTML, not PDF"
    if not content.startswith(b"%PDF-"):
        return "response missing PDF header"

    ct = (content_type or "").lower()
    if ct and "pdf" not in ct and "octet-stream" not in ct and "application/download" not in ct:
        # Some servers send generic type but still return valid pdf; allow if magic bytes are present.
        pass

    return None


def validate_pdf_text(content: bytes, expected_title: str) -> str | None:
    try:
        doc = fitz.open(stream=content, filetype="pdf")
        text_parts: list[str] = []
        for page_index in range(min(2, doc.page_count)):
            try:
                text_parts.append(doc[page_index].get_text()[:4000])
            except Exception:
                continue
    except Exception as exc:  # noqa: BLE001
        return f"pdf parse failed: {exc}"

    text = "\n".join(text_parts).strip()
    if len(text) < 250:
        return "pdf text too small to be a useful legal source"

    doc_tokens = _norm_tokens(text)
    title_tokens = _title_keywords(expected_title)
    if title_tokens:
        overlap = title_tokens.intersection(doc_tokens)
        min_matches = 2 if len(title_tokens) >= 3 else 1
        if len(overlap) < min_matches:
            return f"pdf content does not appear to match expected source: {expected_title}"

    return None


def existing_file_issue(file_path: Path, expected_title: str | None = None) -> str | None:
    if not file_path.exists():
        return "file does not exist"
    data = file_path.read_bytes()
    if not data:
        return "empty file"
    sniff = data[:1024]
    if sniff.startswith(b"<") or b"<html" in sniff.lower():
        return "looks like HTML, not PDF"
    if not sniff.startswith(b"%PDF-"):
        return "missing PDF header"

    if expected_title:
        text_issue = validate_pdf_text(data, expected_title)
        if text_issue:
            return text_issue
    return None


def quarantine_invalid_file(file_path: Path, reason: str) -> Path | None:
    try:
        base = file_path.parents[1] if len(file_path.parents) > 1 else Path("pdfs")
        domain = file_path.parent.name
        quarantine_root = base / "_invalid" / domain
        quarantine_root.mkdir(parents=True, exist_ok=True)

        target = quarantine_root / file_path.name
        if target.exists():
            stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
            target = quarantine_root / f"{target.stem}_{stamp}{target.suffix}"

        file_path.replace(target)
        note = target.with_suffix(target.suffix + ".reason.txt")
        note.write_text(reason, encoding="utf-8")
        return target
    except Exception:
        return None


def _extract_pdf_links(html: str, base_url: str, title: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    title_tokens = _norm_tokens(title)

    candidates: dict[str, int] = {}
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href:
            continue

        absolute = urljoin(base_url, href)
        lowered = absolute.lower()
        anchor_text = (a.get_text(" ", strip=True) or "").lower()

        if not _is_potential_pdf_url(absolute):
            continue

        score = 0
        haystack_tokens = _norm_tokens(lowered + " " + anchor_text)
        score += len(title_tokens.intersection(haystack_tokens))

        host = urlparse(absolute).netloc.lower()
        if "indiacode" in host or "legislative" in host or host.endswith(".gov.in"):
            score += 3
        if lowered.endswith(".pdf"):
            score += 2
        if "/bitstream/" in lowered:
            score += 1

        prev = candidates.get(absolute)
        if prev is None or score > prev:
            candidates[absolute] = score

    ranked = sorted(candidates.items(), key=lambda x: x[1], reverse=True)
    return [url for url, _ in ranked]


def _fetch_once(url: str, session: requests.Session) -> tuple[bytes, str | None, str | None, int]:
    resp = session.get(
        url,
        timeout=DOWNLOAD_TIMEOUT,
        headers=REQUEST_HEADERS,
        allow_redirects=True,
        verify=not ALLOW_INSECURE_SSL,
    )
    return resp.content, resp.headers.get("content-type"), str(resp.url), resp.status_code


def _is_potential_pdf_url(url: str) -> bool:
    lowered = url.lower()
    if "/help/" in lowered or "userguide" in lowered:
        return False
    return lowered.endswith(".pdf") or ".pdf?" in lowered or "/bitstream/" in lowered or "download" in lowered


def _try_download_pdf(url: str, title: str, session: requests.Session, max_scraped_links: int = 8) -> tuple[bytes, str | None, list[str]]:
    errors: list[str] = []

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            content, content_type, final_url, status_code = _fetch_once(url, session)
            if status_code >= 400:
                raise requests.HTTPError(f"http {status_code} for {final_url}")

            issue = validate_pdf_payload(content, content_type)
            if issue is None:
                text_issue = validate_pdf_text(content, title)
                if text_issue is None:
                    return content, final_url, errors
                issue = text_issue

            # Not a PDF directly; attempt scraping for candidate links.
            html = content.decode("utf-8", errors="replace")
            scraped_links = _extract_pdf_links(html, final_url or url, title)
            if not scraped_links:
                raise ValueError(issue)

            for scraped in scraped_links[:max_scraped_links]:
                try:
                    child_content, child_type, child_final_url, child_status = _fetch_once(scraped, session)
                    if child_status >= 400:
                        continue
                    child_issue = validate_pdf_payload(child_content, child_type)
                    if child_issue is None:
                        text_issue = validate_pdf_text(child_content, title)
                        if text_issue is None:
                            return child_content, child_final_url, errors
                except Exception:
                    continue

            raise ValueError(f"{issue}; scrape did not find valid PDF")
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SEC * attempt)

    return b"", None, errors


def download_all(base_folder: str = "./pdfs"):
    base = Path(base_folder)
    success: list[str] = []
    failed: list[dict] = []
    quarantined: list[tuple[str, str, str]] = []

    with requests.Session() as session:
        total = len(PDF_TARGETS)
        for idx, (rel_path, spec) in enumerate(PDF_TARGETS.items(), start=1):
            dest = base / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)

            title = spec.get("title", rel_path)
            candidate_urls = [u for u in spec.get("candidates", []) if isinstance(u, str) and u.strip()]

            if dest.exists():
                issue = existing_file_issue(dest, title)
                if issue is None:
                    print(f"[{idx:02d}/{total}] already exists and valid - skipping {dest.name}")
                    success.append(rel_path)
                    continue

                moved_to = quarantine_invalid_file(dest, issue)
                if moved_to is not None:
                    quarantined.append((rel_path, str(moved_to), issue))
                    print(f"[{idx:02d}/{total}] existing file invalid ({issue}) - moved to {moved_to.name}")
                else:
                    print(f"[{idx:02d}/{total}] existing file invalid ({issue}) - retrying overwrite")

            print(f"[{idx:02d}/{total}] downloading {dest.name}...")
            downloaded = False
            attempt_errors: list[str] = []
            final_used_url = None

            for candidate in candidate_urls:
                content, resolved_url, errors = _try_download_pdf(candidate, title, session)
                attempt_errors.extend([f"{candidate} -> {e}" for e in errors])
                if content:
                    dest.write_bytes(content)
                    final_used_url = resolved_url or candidate
                    size_kb = len(content) // 1024
                    print(f"        saved {dest.name} ({size_kb} KB) from {final_used_url}")
                    success.append(rel_path)
                    downloaded = True
                    break

            if not downloaded:
                reason = "; ".join(attempt_errors[-5:]) if attempt_errors else "no candidate URL configured"
                print(f"        FAILED {dest.name}: {reason}")
                failed.append({
                    "file": rel_path,
                    "title": title,
                    "reason": reason,
                    "candidates": candidate_urls,
                })

            time.sleep(0.4)

    print(f"\n=== Done: {len(success)} ok, {len(quarantined)} quarantined, {len(failed)} failed ===")

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "base_folder": str(base.resolve()),
        "summary": {
            "ok": len(success),
            "quarantined": len(quarantined),
            "failed": len(failed),
        },
        "success": success,
        "quarantined": [
            {"file": f, "moved_to": moved, "reason": reason}
            for f, moved, reason in quarantined
        ],
        "failed": failed,
    }

    report_path = base / "download_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Report written: {report_path}")


if __name__ == "__main__":
    download_all()
