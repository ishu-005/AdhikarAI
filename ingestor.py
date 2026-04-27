import hashlib
import json
import re
import yaml
import logging
import os
from functools import lru_cache
import fitz                          # PyMuPDF
import requests
import urllib3
from bs4 import BeautifulSoup
from pathlib import Path
from datetime import datetime, UTC
from sentence_transformers import SentenceTransformer
import chromadb
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

load_dotenv()

# ── setup ──────────────────────────────────────────────────────────────
HASH_FILE = Path("crawl_hashes.json")
logger = logging.getLogger("adhikarai.ingestor")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_store")
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "lexrag")
client = chromadb.PersistentClient(path=CHROMA_PATH)

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-large")
EMBEDDING_MODEL_FALLBACK = os.getenv("EMBEDDING_MODEL_FALLBACK", "sentence-transformers/all-MiniLM-L6-v2")
ALLOW_INSECURE_SSL = os.getenv("ALLOW_INSECURE_SSL", "false").lower() == "true"
if ALLOW_INSECURE_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _slugify(text: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in text.lower()).strip("_")


class HashingEmbedder:
    dimension = 384

    def encode(self, texts, show_progress_bar: bool = False):  # noqa: ARG002
        vectors = []
        for text in texts:
            vector = [0.0] * self.dimension
            tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
            for token in tokens:
                digest = hashlib.md5(token.encode("utf-8")).digest()
                slot = int.from_bytes(digest[:4], "big") % self.dimension
                vector[slot] += 1.0

            norm = sum(value * value for value in vector) ** 0.5 or 1.0
            vectors.append([value / norm for value in vector])

        return vectors


@lru_cache
def get_embedding_stack() -> tuple[str, SentenceTransformer]:
    try:
        return EMBEDDING_MODEL, SentenceTransformer(
            EMBEDDING_MODEL,
            model_kwargs={"low_cpu_mem_usage": True},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Primary embedding model failed to load: %s", exc)
        if EMBEDDING_MODEL_FALLBACK == "hashing-384-v1" or "paging file" in str(exc).lower() or "out of memory" in str(exc).lower():
            logger.warning("Using local hashing fallback: %s", EMBEDDING_MODEL_FALLBACK)
            return EMBEDDING_MODEL_FALLBACK, HashingEmbedder()

        logger.warning("Falling back to smaller model: %s", EMBEDDING_MODEL_FALLBACK)
        try:
            return EMBEDDING_MODEL_FALLBACK, SentenceTransformer(
                EMBEDDING_MODEL_FALLBACK,
                model_kwargs={"low_cpu_mem_usage": True},
            )
        except Exception as fallback_exc:  # noqa: BLE001
            logger.warning("Embedding fallback also failed: %s", fallback_exc)
            logger.warning("Using local hashing fallback: hashing-384-v1")
            return "hashing-384-v1", HashingEmbedder()


@lru_cache
def get_embedder() -> SentenceTransformer:
    return get_embedding_stack()[1]


@lru_cache
def get_collection() -> chromadb.Collection:
    model_name = get_embedding_stack()[0]
    collection_name = CHROMA_COLLECTION if model_name == EMBEDDING_MODEL else f"{CHROMA_COLLECTION}__{_slugify(model_name)}"
    return client.get_or_create_collection(collection_name)

def load_hashes() -> dict:
    if not HASH_FILE.exists() or HASH_FILE.stat().st_size == 0:
        return {}
    try:
        return json.loads(HASH_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("crawl_hashes.json is invalid JSON, continuing with empty hash state")
        return {}

def save_hashes(h: dict):
    HASH_FILE.write_text(json.dumps(h, indent=2), encoding="utf-8")

def embed_and_store(chunks: list[str], metadatas: list[dict]):
    """Embed a list of text chunks and upsert into ChromaDB."""
    if not chunks:
        logger.info("No chunks to store")
        return

    if len(chunks) != len(metadatas):
        raise ValueError("chunks and metadatas must have the same length")

    # Build deterministic, collision-safe ids.
    # This prevents DuplicateIDError when repeated chunk text appears in one source,
    # while keeping reruns idempotent (same source/chunk -> same id).
    occurrence_by_base: dict[str, int] = {}
    ids: list[str] = []
    for chunk, meta in zip(chunks, metadatas):
        source = str(meta.get("source", "unknown"))
        source_ref = str(meta.get("url") or meta.get("filename") or "unknown")
        domain = str(meta.get("domain", "unknown"))
        section = str(meta.get("section") or meta.get("label") or "")
        chunk_hash = hashlib.md5(chunk.encode("utf-8")).hexdigest()

        base_key = f"{source}|{source_ref}|{domain}|{section}|{chunk_hash}"
        occurrence = occurrence_by_base.get(base_key, 0)
        occurrence_by_base[base_key] = occurrence + 1

        stable_id = hashlib.md5(f"{base_key}|{occurrence}".encode("utf-8")).hexdigest()
        ids.append(stable_id)

    vectors = get_embedder().encode(chunks, show_progress_bar=False)
    if hasattr(vectors, "tolist"):
        vectors = vectors.tolist()
    get_collection().upsert(documents=chunks, embeddings=vectors,
                metadatas=metadatas, ids=ids)
    print(f"  stored {len(chunks)} chunks")

# ── TRACK A: static PDFs ───────────────────────────────────────────────
def ingest_pdf(pdf_path: str, domain: str):
    """Parse a PDF, split by section, embed and store. Run once."""
    path   = Path(pdf_path)
    doc    = fitz.open(str(path))
    chunks, metas = [], []

    current_section, buffer = "", []

    for page in doc:
        for line in page.get_text().splitlines():
            line = line.strip()
            if not line:
                continue
            # treat short ALL-CAPS or numbered lines as section headers
            if (line.isupper() or line[:3].rstrip(". ").isdigit()) and len(line) < 80:
                if buffer:
                    text = " ".join(buffer).strip()
                    if len(text) > 80:          # skip tiny fragments
                        chunks.append(text)
                        metas.append({
                            "source": "pdf",
                            "filename": path.name,
                            "domain": domain,
                            "section": current_section,
                            "ingested_at": datetime.now(UTC).isoformat()
                        })
                    buffer = []
                current_section = line
            else:
                buffer.append(line)

    # flush last section
    if buffer:
        text = " ".join(buffer).strip()
        if len(text) > 80:
            chunks.append(text)
            metas.append({
                "source": "pdf", "filename": path.name,
                "domain": domain, "section": current_section,
                "ingested_at": datetime.now(UTC).isoformat()
            })

    embed_and_store(chunks, metas)
    print(f"[PDF] {path.name} -> {len(chunks)} chunks")


def detect_pdf_issue(pdf_path: Path) -> str | None:
    """Return a human-readable issue if file is not a usable PDF, else None."""
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


def quarantine_invalid_pdf(pdf_path: Path, reason: str) -> Path | None:
    """Move invalid files to pdfs/_invalid/<domain>/ while preserving the original file."""
    try:
        domain = pdf_path.parent.name
        invalid_root = Path("pdfs") / "_invalid" / domain
        invalid_root.mkdir(parents=True, exist_ok=True)

        target = invalid_root / pdf_path.name
        if target.exists():
            stem = target.stem
            suffix = target.suffix
            stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
            target = invalid_root / f"{stem}_{stamp}{suffix}"

        pdf_path.replace(target)
        note_file = target.with_suffix(target.suffix + ".reason.txt")
        note_file.write_text(reason, encoding="utf-8")
        return target
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unable to quarantine invalid PDF %s: %s", pdf_path, exc)
        return None

def ingest_all_pdfs(pdf_folder: str = "./pdfs"):
    """
    Folder structure:  pdfs/criminal_law/BNS.pdf
                       pdfs/consumer/Consumer_Protection.pdf
    Domain is taken from the subfolder name.
    """
    failed_files: list[tuple[str, str]] = []

    for pdf in Path(pdf_folder).rglob("*.pdf"):
        if "_invalid" in pdf.parts:
            continue
        domain = pdf.parent.name
        print(f"[PDF] ingesting {pdf.name} ({domain})")
        issue = detect_pdf_issue(pdf)
        if issue:
            moved_to = quarantine_invalid_pdf(pdf, issue)
            msg = issue if moved_to is None else f"{issue}; moved to {moved_to}"
            failed_files.append((str(pdf), msg))
            print(f"[PDF] skipped invalid file: {pdf} ({msg})")
            continue
        try:
            ingest_pdf(str(pdf), domain)
        except Exception as exc:  # noqa: BLE001
            failed_files.append((str(pdf), str(exc)))
            print(f"[PDF] skipped unreadable file: {pdf} ({exc})")

    if failed_files:
        print("\n[PDF] completed with skipped files:")
        for file_path, reason in failed_files:
            print(f"  - {file_path}: {reason}")

# ── TRACK B: dynamic web links ─────────────────────────────────────────
def fetch_and_clean(url: str) -> str:
    """Fetch a URL, strip HTML boilerplate, return plain text."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        resp = requests.get(url, timeout=15, headers=headers)
    except requests.exceptions.SSLError:
        if not ALLOW_INSECURE_SSL:
            raise
        logger.warning("Retrying with SSL verification disabled for %s", url)
        resp = requests.get(url, timeout=15, headers=headers, verify=False)

    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    # remove nav, footer, scripts
    for tag in soup(["script","style","nav","footer","header","aside"]):
        tag.decompose()
    return " ".join(soup.get_text(separator=" ").split())

def chunk_text(text: str, size: int = 500, overlap: int = 50) -> list[str]:
    words  = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunks.append(" ".join(words[i : i + size]))
        i += size - overlap
    return [c for c in chunks if len(c) > 100]

def crawl_dynamic_sources():
    """Called by scheduler. Only re-embeds pages that have changed."""
    # Warm up model and collection once per run for predictable latency.
    get_embedder()
    get_collection()

    with open("links.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    dynamic_sources = config.get("dynamic_sources", [])

    hashes = load_hashes()

    for source in dynamic_sources:
        if source.get("enabled", True) is False:
            continue

        url = source.get("url")
        domain = source.get("domain", "general")
        label = source.get("label", "source")
        if not url:
            logger.warning("Skipping source with missing URL: %s", source)
            continue
        print(f"[WEB] checking {label}...")

        try:
            text     = fetch_and_clean(url)
            new_hash = hashlib.md5(text.encode()).hexdigest()

            if hashes.get(url) == new_hash:
                print("  no change - skipping")
                continue

            # Content changed (or first run): delete old chunks and store new ones.
            existing = get_collection().get(where={"url": url})
            if existing["ids"]:
                get_collection().delete(ids=existing["ids"])
                print(f"  deleted {len(existing['ids'])} stale chunks")

            chunks = chunk_text(text)
            metas  = [{
                "source":      "web",
                "url":         url,
                "domain":      domain,
                "label":       label,
                "ingested_at": datetime.now(UTC).isoformat()
            } for _ in chunks]

            embed_and_store(chunks, metas)
            hashes[url] = new_hash
            print(f"  updated {label} -> {len(chunks)} chunks")

        except Exception as e:
            print(f"  ERROR on {url}: {e}")

    save_hashes(hashes)

# ── SCHEDULER: runs crawl automatically ───────────────────────────────
def start_scheduler():
    interval_hours = int(os.getenv("CRAWL_INTERVAL_HOURS", "24"))
    scheduler = BackgroundScheduler()
    scheduler.add_job(crawl_dynamic_sources, "interval", hours=interval_hours)
    scheduler.start()
    print(f"[Scheduler] dynamic crawl will run every {interval_hours} hours")
    return scheduler

# ── ENTRYPOINT ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== LexRAG Ingestion ===")

    # Track A: run once for all PDFs in ./pdfs/
    print("\n[1/2] Ingesting static PDFs...")
    ingest_all_pdfs("./pdfs")

    # Track B: first crawl immediately, then schedule
    print("\n[2/2] Crawling dynamic web sources...")
    crawl_dynamic_sources()

    # keep scheduler running (if used as a long-running service)
    scheduler = start_scheduler()
    try:
        import time

        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        scheduler.shutdown()
        print("[Scheduler] stopped")