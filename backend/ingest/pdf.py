"""PDF parsing -> clean, section-aware chunks for Indian bare acts.

Accuracy-focused chunking:
- strips page furniture (page numbers, Gazette headers, margin notes)
- detects the act title and CHAPTER headings
- splits on numbered sections ("12.", "12A.") so each legal provision stays
  one coherent, citable chunk
- prefixes every chunk with "<Act> — <Chapter> — Section <n>" so the embedded
  text itself carries provenance (better retrieval + clearer citations)
- falls back to generic heading/window chunking for non-act PDFs
"""
from __future__ import annotations

import io
import re
from datetime import UTC, datetime
from pathlib import Path

import fitz  # PyMuPDF

from backend.core.logging import get_logger
from backend.ingest.store import embed_and_store, delete_documents_for_filename

logger = get_logger("ingest.pdf")

MAX_CHUNK_CHARS = 1800
MIN_CHUNK_CHARS = 120

_FURNITURE = re.compile(
    r"^(\d{1,4}|page \d+|THE GAZETTE OF INDIA.*|EXTRAORDINARY|PART II.*|"
    r"SEC\.?\s*\d+.*\]|\[.*PART II|REGISTERED NO\..*|website\s*:.*|"
    r"published by authority.*)$",
    re.IGNORECASE,
)
_CHAPTER = re.compile(r"^CHAPTER\s+([IVXLCDM]+|\d+)\b[.\s]*(.*)$", re.IGNORECASE)
_SECTION = re.compile(r"^(\d{1,3}[A-Z]{0,2})\.\s+(.+)$")


def _clean_lines(doc: "fitz.Document") -> list[str]:
    lines: list[str] = []
    for page in doc:
        for raw in page.get_text().splitlines():
            line = raw.strip()
            if not line or _FURNITURE.match(line):
                continue
            lines.append(line)
    return lines


def _detect_title(lines: list[str], filename: str) -> str:
    for line in lines[:60]:
        upper = line.upper()
        if len(line) > 12 and ("ACT" in upper or "ADHINIYAM" in upper or "CONSTITUTION" in upper) and line == upper:
            return line.title().strip()
    return Path(filename).stem.replace("_", " ")


def _window_chunks(text: str, size: int = MAX_CHUNK_CHARS, overlap: int = 200) -> list[str]:
    words = text.split()
    out, current, length = [], [], 0
    for word in words:
        current.append(word)
        length += len(word) + 1
        if length >= size:
            out.append(" ".join(current))
            current = current[-overlap // 6 :]  # word-level overlap
            length = sum(len(w) + 1 for w in current)
    if current and length > MIN_CHUNK_CHARS:
        out.append(" ".join(current))
    return out


def parse_pdf(doc: "fitz.Document", filename: str, domain: str) -> tuple[list[str], list[dict]]:
    lines = _clean_lines(doc)
    act_title = _detect_title(lines, filename)

    chunks: list[str] = []
    metas: list[dict] = []
    chapter = ""
    section_no, section_head, buffer = "", "", []

    def meta(section_label: str, part: int | None = None) -> dict:
        return {
            "source": "pdf",
            "filename": filename,
            "domain": domain,
            "title": act_title,
            "section": section_label + (f" (part {part})" if part else ""),
            "ingested_at": datetime.now(UTC).isoformat(),
        }

    def flush() -> None:
        nonlocal buffer
        if not buffer:
            return
        body = " ".join(buffer).strip()
        buffer = []
        if len(body) < MIN_CHUNK_CHARS:
            return
        label = f"Section {section_no}: {section_head}" if section_no else (chapter or "Preliminary")
        context = " — ".join(x for x in (act_title, chapter, label if section_no else "") if x)
        pieces = _window_chunks(body) if len(body) > MAX_CHUNK_CHARS else [body]
        for idx, piece in enumerate(pieces, start=1):
            chunks.append(f"{context}\n{piece}")
            metas.append(meta(label, part=idx if len(pieces) > 1 else None))

    for line in lines:
        chap = _CHAPTER.match(line)
        if chap:
            flush()
            chapter = f"Chapter {chap.group(1).upper()}" + (f" — {chap.group(2).strip()}" if chap.group(2).strip() else "")
            section_no, section_head = "", ""
            continue
        sec = _SECTION.match(line)
        if sec:
            flush()
            section_no = sec.group(1)
            section_head = sec.group(2).strip().rstrip(".—-")
            buffer.append(line)
            continue
        buffer.append(line)
    flush()

    sections_found = sum(1 for m in metas if m["section"].startswith("Section"))
    if sections_found >= 3:
        logger.info("[PDF] %s: section-aware chunking -> %d chunks (%d sections)", filename, len(chunks), sections_found)
        return chunks, metas

    # Not a bare act — fall back to window chunking over the whole text.
    body = " ".join(lines)
    fallback_chunks = _window_chunks(body)
    fallback_metas = [
        {
            "source": "pdf",
            "filename": filename,
            "domain": domain,
            "title": act_title,
            "section": f"part {i + 1}",
            "ingested_at": datetime.now(UTC).isoformat(),
        }
        for i in range(len(fallback_chunks))
    ]
    logger.info("[PDF] %s: generic window chunking -> %d chunks", filename, len(fallback_chunks))
    return [f"{act_title}\n{c}" for c in fallback_chunks], fallback_metas


def ingest_pdf_file(pdf_path: str | Path, domain: str) -> int:
    path = Path(pdf_path)
    with fitz.open(str(path)) as doc:
        chunks, metas = parse_pdf(doc, path.name, domain)
    delete_documents_for_filename(path.name)  # re-ingestion must not duplicate
    stored = embed_and_store(chunks, metas)
    logger.info("[PDF] %s -> %d chunks", path.name, len(chunks))
    return stored


def ingest_pdf_bytes(data: bytes, filename: str, domain: str) -> int:
    with fitz.open(stream=io.BytesIO(data), filetype="pdf") as doc:
        chunks, metas = parse_pdf(doc, filename, domain)
    delete_documents_for_filename(filename)
    stored = embed_and_store(chunks, metas)
    logger.info("[PDF] %s (upload) -> %d chunks", filename, len(chunks))
    return stored


def detect_pdf_issue(pdf_path: Path) -> str | None:
    if not pdf_path.exists() or not pdf_path.is_file():
        return "file does not exist"
    try:
        header = pdf_path.read_bytes()[:1024]
    except Exception as exc:  # noqa: BLE001
        return f"cannot read file bytes: {exc}"
    if not header:
        return "empty file"
    if header.startswith(b"<") or b"<html" in header.lower():
        return "file looks like HTML/error page, not a PDF"
    if not header.startswith(b"%PDF-"):
        return "missing PDF signature header"
    return None


def ingest_all_pdfs(pdf_folder: str = "./pdfs") -> int:
    failed: list[tuple[str, str]] = []
    total_chunks = 0
    for pdf in Path(pdf_folder).rglob("*.pdf"):
        if "_invalid" in pdf.parts:
            continue
        domain = pdf.parent.name
        issue = detect_pdf_issue(pdf)
        if issue:
            failed.append((str(pdf), issue))
            logger.warning("[PDF] skipped invalid file: %s (%s)", pdf, issue)
            continue
        try:
            total_chunks += ingest_pdf_file(pdf, domain)
        except Exception as exc:  # noqa: BLE001
            failed.append((str(pdf), str(exc)))
            logger.warning("[PDF] skipped unreadable file: %s (%s)", pdf, exc)
    if failed:
        logger.info("[PDF] completed with %d skipped files.", len(failed))
    logger.info("[PDF] ingestion complete: %d chunks across all files.", total_chunks)
    return total_chunks
