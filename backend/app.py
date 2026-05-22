import os
import hashlib
import re
import logging
import math
import unicodedata
import uuid
import atexit
import time
import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from functools import lru_cache, wraps
from threading import Lock, Thread

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import yaml
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from supabase import create_client, Client
from fastapi import FastAPI, HTTPException, Request
from fastapi import File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer, CrossEncoder
import uvicorn


logger = logging.getLogger("adhikarai")
if not logger.handlers:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

load_dotenv()


def create_http_session() -> requests.Session:
    session = requests.Session()
    retry_strategy = Retry(total=3, backoff_factor=0.3, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


_http_session: requests.Session | None = None


def get_http_session() -> requests.Session:
    global _http_session
    if _http_session is None:
        _http_session = create_http_session()
    return _http_session


def cleanup_http_session() -> None:
    global _http_session
    if _http_session is not None:
        _http_session.close()
        _http_session = None


atexit.register(cleanup_http_session)

@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_runtime_on_startup(app)
    try:
        yield
    finally:
        cleanup_http_session()


# App and model setup
app = FastAPI(title="GenricAsk RAG API", version="1.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
templates = Jinja2Templates(directory="frontend/templates")

LINKS_FILE = Path("links.yaml")


class Settings(BaseModel):
    collection_name: str = os.getenv("COLLECTION_NAME", "legal_documents")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-large")
    embedding_model_fallback: str = os.getenv("EMBEDDING_MODEL_FALLBACK", "sentence-transformers/all-MiniLM-L6-v2")
    groq_api_key: str = os.getenv("GROQ_API_KEY", "").strip()
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    groq_model_fallback: str = os.getenv("GROQ_MODEL_FALLBACK", "llama-3.1-8b-instant")
    groq_models: str = os.getenv("GROQ_MODELS", "").strip()
    reranker_model: str = os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
    reranker_enabled: bool = os.getenv("RERANKER_ENABLED", "true").lower() == "true"
    max_query_chars: int = int(os.getenv("MAX_QUERY_CHARS", "4000"))
    upload_max_mb: int = int(os.getenv("UPLOAD_MAX_MB", "20"))
    allowed_origins: str = os.getenv("ALLOWED_ORIGINS", "*")
    allowed_upload_domains: str = os.getenv(
        "ALLOWED_UPLOAD_DOMAINS",
        "criminal_law,consumer,labour,rti,human_rights,citizen_rights,women_family,property_finance,case_law,legislation,grievance",
    )
    use_supabase: bool = os.getenv("USE_SUPABASE", "true").lower() == "true"
    # Supabase Vector DB (pgvector)
    supabase_url: str = os.getenv("SUPABASE_URL", "").strip()
    supabase_api_key: str = os.getenv("SUPABASE_API_KEY", "").strip()
    supabase_bucket_name: str = os.getenv("SUPABASE_BUCKET_NAME", "pdfs")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
origins = [x.strip() for x in settings.allowed_origins.split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ━━━ OPTIMIZATION: Response Caching & Performance ━━━
class OptimizationCache:
    """In-memory cache for frequent queries to reduce API latency"""
    def __init__(self, ttl_seconds: int = 3600):
        self.cache: dict = {}
        self.ttl = ttl_seconds
        self.lock = Lock()
    
    def get_key(self, question: str, domain: str, language: str) -> str:
        """Create deterministic cache key"""
        content = f"{question.lower().strip()}|{domain}|{language}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def get(self, question: str, domain: str, language: str) -> dict | None:
        key = self.get_key(question, domain, language)
        with self.lock:
            if key in self.cache:
                entry, timestamp = self.cache[key]
                if datetime.now(UTC) - timestamp < timedelta(seconds=self.ttl):
                    return entry
                del self.cache[key]
        return None
    
    def set(self, question: str, domain: str, language: str, entry: dict) -> None:
        key = self.get_key(question, domain, language)
        with self.lock:
            self.cache[key] = (entry, datetime.now(UTC))
    
    def clear_old(self) -> None:
        """Cleanup expired entries"""
        now = datetime.now(UTC)
        with self.lock:
            expired = [k for k, (_, ts) in self.cache.items() if now - ts > timedelta(seconds=self.ttl)]
            for k in expired:
                del self.cache[k]

opt_cache = OptimizationCache(ttl_seconds=1800)  # 30-minute cache


# ━━━ SUPABASE PGVECTOR CLIENT ━━━
def get_supabase_client() -> Client:
    """Get or create Supabase client for pgvector queries"""
    if not hasattr(app.state, 'supabase_client'):
        settings = get_settings()
        app.state.supabase_client = create_client(
            settings.supabase_url,
            settings.supabase_api_key
        )
    return app.state.supabase_client


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def get_allowed_domains() -> set[str]:
    settings = get_settings()
    return {d.strip().lower() for d in settings.allowed_upload_domains.split(",") if d.strip()}


class HashingEmbedder:
    dimension = 1024

    def encode(self, texts, show_progress_bar: bool = False):  # noqa: ARG002
        vectors = []
        for text in texts:
            vector = [0.0] * self.dimension
            tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
            for token in tokens:
                slot = int.from_bytes(hashlib.md5(token.encode("utf-8")).digest()[:4], "big") % self.dimension
                vector[slot] += 1.0

            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            vectors.append([value / norm for value in vector])

        return vectors


@lru_cache
def get_embedding_stack() -> tuple[str, SentenceTransformer]:
    settings = get_settings()
    try:
        return settings.embedding_model, SentenceTransformer(
            settings.embedding_model,
            model_kwargs={"low_cpu_mem_usage": True},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Primary embedding model failed to load: %s", exc)
        if settings.embedding_model_fallback == "hashing-1024-v1" or "paging file" in str(exc).lower() or "out of memory" in str(exc).lower():
            logger.warning("Using local hashing fallback: %s", settings.embedding_model_fallback)
            return settings.embedding_model_fallback, HashingEmbedder()

        logger.warning("Falling back to smaller model: %s", settings.embedding_model_fallback)
        try:
            return settings.embedding_model_fallback, SentenceTransformer(
                settings.embedding_model_fallback,
                model_kwargs={"low_cpu_mem_usage": True},
            )
        except Exception as fallback_exc:  # noqa: BLE001
            logger.warning("Embedding fallback also failed: %s", fallback_exc)
            logger.warning("Using local hashing fallback: hashing-1024-v1")
            return "hashing-1024-v1", HashingEmbedder()


@lru_cache
def get_embedder() -> SentenceTransformer:
    return get_embedding_stack()[1]


def normalize_embedding(vector: list[float], target_dimension: int = 1024) -> list[float]:
    if len(vector) == target_dimension:
        return vector
    if len(vector) > target_dimension:
        return vector[:target_dimension]
    return vector + [0.0] * (target_dimension - len(vector))


@lru_cache
def get_reranker() -> CrossEncoder | None:
    settings = get_settings()
    if not settings.reranker_enabled:
        return None
    try:
        return CrossEncoder(settings.reranker_model)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Reranker model failed to load (%s), continuing without reranker", exc)
        return None


@lru_cache
def get_collection_name() -> str:
    settings = get_settings()
    resolved_model = get_embedding_stack()[0]
    if resolved_model == settings.embedding_model:
        return settings.collection_name
    return f"{settings.collection_name}__{_slugify(resolved_model)}"

DOMAIN_KEYWORDS = {
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

DOMAIN_ALIASES = {
    "women": "women_family",
    "women_rights": "women_family",
    "case-law": "case_law",
    "laws": "legislation",
}

HINDI_HINTS = {
    "क्या",
    "कैसे",
    "कब",
    "कहां",
    "कहाँ",
    "क्यों",
    "मुझे",
    "मेरा",
    "मेरे",
    "कानून",
    "अधिकार",
    "पुलिस",
    "शिकायत",
    "अरेस्ट",
    "जमानत",
    "एफआईआर",
}


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=get_settings().max_query_chars)
    language: str | None = Field(default=None)
    conversation_id: str | None = Field(default=None)


def normalize_domain(domain: str) -> str:
    lowered = normalize_text(domain).lower().replace(" ", "_")
    lowered = re.sub(r"[^a-z0-9_\-]", "", lowered)
    lowered = lowered.replace("-", "_")
    return DOMAIN_ALIASES.get(lowered, lowered)


def get_domain_catalog() -> list[str]:
    domains = set(get_allowed_domains())
    for domain in DOMAIN_KEYWORDS:
        domains.add(domain)
    for source in load_links_config():
        domain = normalize_domain(str(source.get("domain", "")))
        if domain:
            domains.add(domain)

    # Keep deterministic order for UI.
    return sorted(domains)


def get_chat_store() -> tuple[dict[str, list[dict]], Lock]:
    if not hasattr(app.state, "chat_threads"):
        app.state.chat_threads = {}
    if not hasattr(app.state, "chat_lock"):
        app.state.chat_lock = Lock()
    return app.state.chat_threads, app.state.chat_lock


def get_supabase_client():
    """Get or create Supabase client if configured."""
    settings = get_settings()
    if not settings.use_supabase or not settings.supabase_url or not settings.supabase_api_key:
        return None
    
    if not hasattr(app.state, "supabase_client"):
        try:
            app.state.supabase_client = create_client(settings.supabase_url, settings.supabase_api_key)
        except Exception as e:
            logger.warning(f"Failed to initialize Supabase: {e}. Falling back to local storage.")
            return None
    
    return getattr(app.state, "supabase_client", None)


def _load_chats_from_supabase() -> dict[str, list[dict]]:
    """Load all chats from Supabase."""
    try:
        supabase = get_supabase_client()
        if not supabase:
            return {}
        
        response = supabase.table("chats").select("id, messages").execute()
        chats = {}
        for row in response.data:
            chats[row["id"]] = row.get("messages", [])
        return chats
    except Exception as e:
        logger.warning(f"Failed to load chats from Supabase: {e}")
        return {}


def _save_chat_to_supabase(conversation_id: str, messages: list[dict]) -> bool:
    """Save chat to Supabase."""
    try:
        supabase = get_supabase_client()
        if not supabase:
            return False
        
        supabase.table("chats").upsert({"id": conversation_id, "messages": messages}).execute()
        return True
    except Exception as e:
        logger.warning(f"Failed to save chat to Supabase: {e}")
        return False


def create_conversation() -> str:
    store, lock = get_chat_store()
    convo_id = uuid.uuid4().hex
    with lock:
        store[convo_id] = []
    
    # Also save to Supabase if enabled
    _save_chat_to_supabase(convo_id, [])
    
    return convo_id


def append_message(conversation_id: str, role: str, content: str, meta: dict | None = None) -> None:
    store, lock = get_chat_store()
    message = {
        "role": role,
        "content": content,
        "created_at": datetime.now(UTC).isoformat(),
        "meta": meta or {},
    }
    with lock:
        if conversation_id not in store:
            store[conversation_id] = []
        store[conversation_id].append(message)
    
    # Also save to Supabase if enabled
    with lock:
        messages = store.get(conversation_id, [])
    _save_chat_to_supabase(conversation_id, messages)


def get_conversation(conversation_id: str) -> list[dict]:
    store, lock = get_chat_store()
    with lock:
        messages = store.get(conversation_id, [])
        return list(messages)


def initialize_runtime_on_startup(app_instance: FastAPI) -> None:
    ensure_runtime_initialized()
    
    # Load existing chats from Supabase if enabled
    settings = get_settings()
    if settings.use_supabase:
        try:
            chats = _load_chats_from_supabase()
            store, lock = get_chat_store()
            with lock:
                store.update(chats)
            logger.info(f"Loaded {len(chats)} chats from Supabase")
        except Exception as e:
            logger.warning(f"Failed to load chats from Supabase on startup: {e}")


def ensure_runtime_initialized() -> None:
    """Initialize embedder and Supabase client"""
    settings = get_settings()
    did_init = False
    
    # Initialize embedder
    if not hasattr(app.state, "embedder"):
        app.state.embedder = get_embedder()
        logger.info("Embedder initialized")
    
    # Initialize Supabase client for pgvector
    if not hasattr(app.state, "supabase_client"):
        get_supabase_client()
        logger.info("Supabase pgvector client initialized")
    
    # Initialize Supabase if configured
    if settings.use_supabase and settings.supabase_url and settings.supabase_api_key:
        if not hasattr(app.state, "supabase_client"):
            try:
                app.state.supabase_client = create_client(settings.supabase_url, settings.supabase_api_key)
                logger.info("Supabase client initialized")
                did_init = True
            except Exception as e:
                logger.warning(f"Failed to initialize Supabase: {e}. Falling back to local storage.")

    if did_init:
        logger.info("Initialization complete")


def load_links_config() -> list[dict]:
    if not LINKS_FILE.exists():
        return []
    with LINKS_FILE.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("dynamic_sources", [])


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def detect_language(question: str) -> str:
    normalized = normalize_text(question)
    if not normalized:
        return "en"

    if any("DEVANAGARI" in unicodedata.name(char, "") for char in normalized):
        return "hi"

    lowered = normalized.lower()
    if any(f" {hint.lower()} " in f" {lowered} " for hint in HINDI_HINTS):
        return "hi"

    return "en"


def context_source_label(context_chunks: list[str], live_chunks: list[dict]) -> tuple[list[str], str, str]:
    sources = ["local embedding"] if context_chunks else []
    if live_chunks:
        sources.append("websites")

    if not sources:
        return ["general knowledge"], "general knowledge", "No retrieved context found"

    label = " + ".join(sources)
    notice = f"Using {label}"
    return sources, label, notice


def answer_scope_notice(language: str, sources: list[str], context_chunks: list[str], live_chunks: list[dict]) -> str:
    has_context = bool(context_chunks or live_chunks)
    if language == "hi":
        if has_context:
            return f"स्रोत: {' + '.join(sources)}."
        return "मुझे matching context नहीं मिला, इसलिए यह general best-effort उत्तर है."

    if has_context:
        return f"Source: {' + '.join(sources)}."
    return "I could not find matching context, so this is a general best-effort answer."


def language_instruction(language: str) -> str:
    if language == "hi":
        return "Reply in simple Hindi. If the retrieved context does not directly support the answer, say it is a best-effort answer based on your understanding."
    return "Reply in simple English. If the retrieved context does not directly support the answer, say it is a best-effort answer based on your understanding."


def detect_domain(question: str) -> tuple[str, dict]:
    q = question.lower()
    scores = {}
    for domain, words in DOMAIN_KEYWORDS.items():
        scores[domain] = sum(1 for w in words if w in q)

    best_domain = max(scores, key=scores.get)
    if scores[best_domain] == 0:
        best_domain = "general"
    return normalize_domain(best_domain), scores


def vector_retrieve(question: str, domain: str, top_k: int = 5) -> dict:
    """⚡ Retrieve from Supabase pgvector instead of ChromaDB"""
    try:
        ensure_runtime_initialized()
        supabase = get_supabase_client()
        
        # Generate embedding for question
        query_vector = app.state.embedder.encode([question], show_progress_bar=False)
        if hasattr(query_vector, "tolist"):
            query_vector = query_vector.tolist()[0]
        query_vector = normalize_embedding(list(query_vector))
        
        # Query Supabase pgvector
        response = supabase.rpc(
            'search_legal_documents',
            {
                'query_embedding': query_vector,
                'search_domain': domain,
                'match_count': top_k * 2,  # Get extra for reranking
            }
        ).execute()
        
        # Extract results
        docs = []
        metas = []
        dists = []
        
        if response.data:
            for row in response.data:
                docs.append(row.get('content', ''))
                metas.append({
                    'domain': row.get('domain', 'general'),
                    'source': row.get('source', 'database'),
                    'title': row.get('title', ''),
                    'similarity': row.get('similarity', 0)
                })
                # Convert similarity to distance (1 - similarity)
                similarity = row.get('similarity', 0)
                dists.append(max(0.0, 1.0 - float(similarity)))
        
        result = {
            "documents": [docs],
            "metadatas": [metas],
            "distances": [dists]
        }
        
        # Rerank if enabled
        reranker = get_reranker()
        if reranker is not None and docs:
            return _rerank_results(question, result, top_k)
        
        # Return top_k results
        return {
            "documents": [docs[:top_k]],
            "metadatas": [metas[:top_k]],
            "distances": [dists[:top_k]]
        }
        
    except Exception as exc:  # noqa: BLE001
        logger.warning("Vector retrieval from Supabase failed: %s", exc)
        return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

        docs = (merged.get("documents") or [[]])[0]
        metas = (merged.get("metadatas") or [[]])[0]
        dists = (merged.get("distances") or [[]])[0]
        if not docs:
            return merged

        pairs = [[query_text, doc] for doc in docs]
        try:
            scores = reranker.predict(pairs)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Reranker prediction failed, using merged ranking: %s", exc)
            return merged

        ranked_items = []
        for i, score in enumerate(scores):
            md = metas[i] if i < len(metas) and isinstance(metas[i], dict) else {}
            base_dist = dists[i] if i < len(dists) and isinstance(dists[i], (int, float)) else 1.0
            rerank_score = float(score)
            # Keep cross-encoder score for explainability.
            md = {**md, "rerank_score": round(rerank_score, 4)}
            ranked_items.append((rerank_score, docs[i], md, base_dist))

        ranked_items.sort(key=lambda x: x[0], reverse=True)
        ranked_items = ranked_items[:max_k]

        top_score = ranked_items[0][0]
        bottom_score = ranked_items[-1][0]
        score_range = (top_score - bottom_score) or 1.0

        return {
            "documents": [[item[1] for item in ranked_items]],
            "metadatas": [[item[2] for item in ranked_items]],
            # Normalize reranker score to pseudo-distance for existing scoring path.
            "distances": [[max(0.0, 1.0 - ((item[0] - bottom_score) / score_range)) for item in ranked_items]],
        }

    kwargs = {
        "query_embeddings": query_vector,
        "n_results": top_k,
        "include": ["documents", "metadatas", "distances"],
    }

    if domain != "general":
        kwargs["where"] = {"domain": domain}

    results = _run_query(kwargs)
    # Fallback if domain filter has no hits
    if not results.get("documents") or not results["documents"][0]:
        kwargs.pop("where", None)
        results = _run_query(kwargs)

    # Always mix in keyword retrieval to improve recall and reduce brittle misses.
    keyword_results = _keyword_fallback(question, domain, top_k)
    merged = _merge_results(results, keyword_results, max(top_k * 2, 8))
    return _rerank_results(question, merged, top_k)


def fetch_page_text(url: str, timeout: int = 12) -> str:
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": "LexRAG-UI/1.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    return normalize_text(soup.get_text(separator=" "))


def live_fetch_for_domain(domain: str, max_sources: int = 2) -> list[dict]:
    query_domain = normalize_domain(domain)
    links = [
        x
        for x in load_links_config()
        if normalize_domain(str(x.get("domain", ""))) == query_domain
    ][:max_sources]
    fetched = []

    for src in links:
        url = src.get("url", "")
        label = src.get("label", "source")
        if not url:
            continue
        try:
            text = fetch_page_text(url)
            snippet = text[:700]
            fetched.append({"label": label, "url": url, "snippet": snippet})
        except Exception as exc:  # noqa: BLE001
            fetched.append({"label": label, "url": url, "snippet": f"Fetch failed: {exc}"})

    return fetched


def build_context_from_results(results: dict) -> tuple[list[str], list[dict]]:
    docs = (results.get("documents") or [[]])[0]
    metas = (results.get("metadatas") or [[]])[0]
    dists = (results.get("distances") or [[]])[0]

    context = []
    citations = []

    for i, doc in enumerate(docs):
        md = metas[i] if i < len(metas) else {}
        dist = dists[i] if i < len(dists) else None
        score = 1.0 / (1.0 + dist) if isinstance(dist, (float, int)) else None

        section = md.get("section") or md.get("label") or "Reference"
        source = md.get("url") or md.get("filename") or "Unknown source"

        context.append(f"[{i + 1}] {doc}")
        citations.append(
            {
                "id": i + 1,
                "section": section,
                "source": source,
                "domain": md.get("domain", "unknown"),
                "score": round(score, 3) if score is not None else None,
            }
        )

    return context, citations


def fallback_answer(question: str, context_chunks: list[str], live_chunks: list[dict], language: str, sources: list[str]) -> str:
    if language == "hi":
        intro = "प्रश्न"
        guidance_title = "सरल जवाब"
        references_title = "संबंधित संदर्भ"
        live_title = "Live स्रोत"
        no_context = "मुझे exact context नहीं मिला, इसलिए यह best-effort उत्तर है."
        tips = [
            "तथ्य, तारीखें, और सबूत पहले इकट्ठा करें.",
            "सही authority या office में लिखित शिकायत करें.",
            "complaint number, acknowledgement, और response की copy रखें.",
        ]
    else:
        intro = "Question"
        guidance_title = "Plain-language guidance"
        references_title = "Relevant references"
        live_title = "Live source snapshot"
        no_context = "I could not find exact matching context, so this is a best-effort answer."
        tips = [
            "Document facts, dates, and proof first.",
            "Use the right authority or office and file in writing if possible.",
            "Keep copies of complaint numbers, acknowledgements, and responses.",
        ]

    brief_context = "\n".join(context_chunks[:3]) if context_chunks else "No matching legal chunk found."
    live_bits = []
    for item in live_chunks:
        snippet = item.get("snippet", "")
        if snippet:
            live_bits.append(f"- {item.get('label')}: {snippet[:220]}...")

    live_text = "\n".join(live_bits) if live_bits else "No live-source update was available."
    return (
        f"{intro}: {question}\n\n"
        f"{guidance_title}:\n"
        f"1) {tips[0]}\n"
        f"2) {tips[1]}\n"
        f"3) {tips[2]}\n\n"
        f"Context note: {no_context if not (context_chunks or live_chunks) else 'This answer is based on the retrieved context.'}\n"
        f"Context source: {' + '.join(sources)}\n\n"
        f"{references_title}:\n"
        f"{brief_context}\n\n"
        f"{live_title}:\n"
        f"{live_text}\n"
    )


def _call_groq(messages: list[dict], temperature: float = 0.2) -> str:
    settings = get_settings()
    headers = {"Authorization": f"Bearer {settings.groq_api_key}", "Content-Type": "application/json"}

    def _dedupe_keep_order(models: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for item in models:
            model = (item or "").strip()
            if model and model not in seen:
                ordered.append(model)
                seen.add(model)
        return ordered

    def _rank_models(models: list[str]) -> list[str]:
        preferred_order = [
            "llama-3.3-70b-versatile",
            "deepseek-r1-distill-llama-70b",
            "qwen-qwq-32b",
            "mixtral-8x7b-32768",
            "llama-3.1-70b-versatile",
            "llama-3.1-8b-instant",
        ]
        rank = {name: idx for idx, name in enumerate(preferred_order)}
        return sorted(models, key=lambda name: rank.get(name, len(preferred_order) + 100))

    base_candidates = _dedupe_keep_order(
        [
            model.strip() for model in settings.groq_models.split(",") if model.strip()
        ]
        + [settings.groq_model, settings.groq_model_fallback]
    )

    # Default chain when GROQ_MODELS is not set explicitly.
    if not base_candidates:
        base_candidates = [
            "llama-3.3-70b-versatile",
            "deepseek-r1-distill-llama-70b",
            "qwen-qwq-32b",
            "mixtral-8x7b-32768",
            "llama-3.1-70b-versatile",
            "llama-3.1-8b-instant",
        ]

    models_to_try = _rank_models(base_candidates)

    # Try to intersect with available models from API key and keep best-first ranking.
    try:
        session = get_http_session()
        model_resp = session.get(
            "https://api.groq.com/openai/v1/models",
            headers=headers,
            timeout=12,
        )
        model_resp.raise_for_status()
        available = {
            item.get("id", "").strip()
            for item in (model_resp.json().get("data") or [])
            if item.get("id")
        }
        if available:
            matched = [model for model in models_to_try if model in available]
            extras = [model for model in available if model not in matched]
            models_to_try = matched + _rank_models(extras)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not fetch Groq model list, using configured fallback chain: %s", exc)

    last_error: Exception | None = None
    for model_name in models_to_try:
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
        }

        try:
            session = get_http_session()
            resp = session.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=40,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except requests.exceptions.HTTPError as exc:
            last_error = exc
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code in {400, 404, 422} and model_name != models_to_try[-1]:
                logger.warning("Groq model %s failed with %s, trying fallback model", model_name, status_code)
                continue
            raise

    if last_error:
        raise last_error
    raise RuntimeError("Groq generation failed without a specific error")


def generate_answer(
    question: str,
    context_chunks: list[str],
    live_chunks: list[dict],
    language: str,
    sources: list[str],
    context_notice: str,
    conversation_history: list[dict] | None = None,
) -> str:
    """⚡ Optimized answer generation with direct prompt (no analysis step)"""
    settings = get_settings()
    if not settings.groq_api_key:
        return "Groq API key is not set."

    # ⚡ Limit context to top 3 chunks (was 5) to reduce token usage
    context_block = "\n\n".join(context_chunks[:3])
    
    # ⚡ Summarize live sources instead of full snippets
    live_block = ""
    if live_chunks:
        live_block = "\n".join(
            [f"• {x.get('label', 'Source')}: {x.get('snippet', '')[:200]}" for x in live_chunks[:2]]
        )
    
    # ⚡ Use only last 4 conversation items (was 8) to reduce tokens
    history_items = conversation_history or []
    history_window = history_items[-4:] if history_items else []
    history_block = ""
    if history_window:
        history_block = "\n".join(
            [f"{item.get('role', '').title()}: {item.get('content', '')[:100]}" for item in history_window]
        )

    # ⚡ Optimized single-pass prompt (replaces 2-step analysis)
    lang_inst = language_instruction(language)
    
    final_prompt = (
        f"{lang_inst}\n\n"
        "Provide direct, actionable legal guidance based on the following:\n\n"
        f"Question: {question}\n\n"
        f"Context: {context_notice}\n"
        f"{context_block if context_block else 'No document sources found.'}\n\n"
        f"{f'Recent updates: {live_block}' if live_block else ''}\n\n"
        f"{f'Previous discussion: {history_block}' if history_block else ''}\n\n"
        "Format response with:\n"
        "1. Direct answer (2-3 sentences)\n"
        "2. Key steps (bullets)\n"
        "3. Important note about source reliability\n\n"
        "Keep it concise and practical. Not legal advice—general guidance only."
    )

    return _call_groq(
        [
            {"role": "system", "content": "You are a legal guidance assistant for Indian citizens. Be concise, practical, and clear."},
            {"role": "user", "content": final_prompt},
        ],
        temperature=0.2,
    )


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "time": datetime.now(UTC).isoformat(),
        "model_loaded": hasattr(app.state, "embedder"),
        "vector_store_ready": hasattr(app.state, "collection"),
    }


@app.get("/api/sources")
async def sources():
    dynamic = load_links_config()
    return {"dynamic_sources": dynamic}


@app.get("/api/domains")
async def domains():
    return {"domains": get_domain_catalog()}


@app.post("/api/chat/new")
async def new_chat():
    conversation_id = create_conversation()
    return {"conversation_id": conversation_id, "messages": []}


@app.get("/api/chat/{conversation_id}")
async def read_chat(conversation_id: str):
    return {"conversation_id": conversation_id, "messages": get_conversation(conversation_id)}


@app.delete("/api/chat/{conversation_id}")
async def delete_chat(conversation_id: str):
    """Delete a chat conversation from both local and Supabase storage."""
    store, lock = get_chat_store()
    with lock:
        if conversation_id in store:
            del store[conversation_id]
    
    # Also delete from Supabase if enabled
    try:
        supabase = get_supabase_client()
        if supabase:
            supabase.table("chats").delete().eq("id", conversation_id).execute()
    except Exception as e:
        logger.warning(f"Failed to delete chat from Supabase: {e}")
    
    return {"status": "deleted", "conversation_id": conversation_id}


class RenameRequest(BaseModel):
    name: str


@app.put("/api/chat/{conversation_id}/name")
async def rename_chat(conversation_id: str, request: RenameRequest):
    """Rename a chat conversation."""
    if not request.name or not request.name.strip():
        raise HTTPException(status_code=400, detail="name cannot be empty")
    
    # Store name as metadata (simple approach: store in a separate table or in messages meta)
    # For now, we'll update via Supabase if enabled
    try:
        supabase = get_supabase_client()
        if supabase:
            supabase.table("chat_metadata").upsert({
                "id": conversation_id,
                "name": request.name.strip()
            }).execute()
    except Exception as e:
        logger.warning(f"Failed to rename chat in Supabase: {e}")
    
    return {"status": "renamed", "conversation_id": conversation_id, "name": request.name}


@app.get("/api/pdf-status")
async def pdf_status():
    root = Path("pdfs")
    expected_domains = get_domain_catalog()
    status = []

    for domain in expected_domains:
        folder = root / domain
        files = sorted([p.name for p in folder.glob("*.pdf")]) if folder.exists() else []
        status.append(
            {
                "domain": domain,
                "folder": str(folder).replace("\\", "/"),
                "pdf_count": len(files),
                "pdf_files": files,
            }
        )

    return {"pdf_status": status}


@app.post("/api/upload-pdf")
async def upload_pdf(domain: str = Form(...), pdf: UploadFile = File(...)):
    settings = get_settings()
    safe_domain = normalize_domain(domain)
    if not safe_domain:
        raise HTTPException(status_code=400, detail="domain is required")
    if safe_domain in {"_invalid", ".", ".."}:
        raise HTTPException(status_code=400, detail="invalid domain")
    if safe_domain not in get_allowed_domains():
        raise HTTPException(status_code=400, detail="domain not allowed")

    if not pdf.filename or not pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="only .pdf files are allowed")

    folder = Path("pdfs") / safe_domain
    folder.mkdir(parents=True, exist_ok=True)

    filename = Path(pdf.filename).name
    target = folder / filename
    data = await pdf.read()

    max_bytes = settings.upload_max_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"file too large, max upload size is {settings.upload_max_mb} MB",
        )

    target.write_bytes(data)

    return {
        "message": "pdf uploaded",
        "domain": safe_domain,
        "filename": filename,
        "saved_to": str(target).replace("\\", "/"),
        "size_bytes": len(data),
    }


@app.post("/api/query")
async def query(payload: QueryRequest):
    settings = get_settings()
    question = normalize_text(payload.question)

    if not question:
        raise HTTPException(status_code=400, detail="question is required")
    if len(question) > settings.max_query_chars:
        raise HTTPException(status_code=400, detail="question exceeds max size")

    domain, scores = detect_domain(question)
    conversation_id = normalize_text(payload.conversation_id or "")
    if not conversation_id:
        conversation_id = create_conversation()
    
    requested_language = (payload.language or "").strip().lower()
    language = requested_language if requested_language in {"en", "hi"} else detect_language(question)
    
    # ⚡ Check cache first
    cached = opt_cache.get(question, domain, language)
    if cached:
        append_message(conversation_id, role="user", content=question, meta={"language": language, "domain": domain})
        append_message(
            conversation_id,
            role="assistant",
            content=cached["answer"],
            meta={
                "language": language,
                "domain": domain,
                "citations": cached.get("citations", []),
                "context_notice": cached.get("context_notice", ""),
            },
        )
        return {
            "conversation_id": conversation_id,
            "question": question,
            "domain": domain,
            "language": language,
            "context_sources": cached.get("context_sources", []),
            "context_source_label": cached.get("context_source_label", ""),
            "context_notice": cached.get("context_notice", ""),
            "domain_scores": scores,
            "answer": cached["answer"],
            "citations": cached.get("citations", []),
            "live_sources": cached.get("live_sources", []),
            "_cached": True,
        }
    
    prior_messages = get_conversation(conversation_id)
    
    # ⚡ Run vector retrieval and live fetch in parallel
    try:
        retrieval = vector_retrieve(question, domain=domain, top_k=5)
        live_chunks = live_fetch_for_domain(domain) if domain != "general" else []
    except Exception as exc:  # noqa: BLE001
        logger.warning("Retrieval failed: %s", exc)
        retrieval = {"documents": [[]], "metadatas": [[]], "distances": [[]]}
        live_chunks = []
    
    context_chunks, citations = build_context_from_results(retrieval)
    sources, context_label, context_notice = context_source_label(context_chunks, live_chunks)

    try:
        answer = generate_answer(
            question,
            context_chunks,
            live_chunks,
            language,
            sources,
            context_notice,
            prior_messages,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Answer generation failed: %s", exc)
        answer = "Groq API key is not set."

    if answer != "Groq API key is not set." and language == "hi" and not re.search(r"[\u0900-\u097F]", answer):
        answer = fallback_answer(question, context_chunks, live_chunks, language, sources)
        answer += "\n\nनोट: मॉडल ने हिंदी में स्पष्ट उत्तर नहीं दिया, इसलिए हिंदी fallback उत्तर दिया गया है."

    # ⚡ Cache the result
    cache_entry = {
        "answer": answer,
        "context_sources": sources,
        "context_source_label": context_label,
        "context_notice": answer_scope_notice(language, sources, context_chunks, live_chunks),
        "citations": citations,
        "live_sources": live_chunks,
    }
    opt_cache.set(question, domain, language, cache_entry)

    append_message(
        conversation_id,
        role="user",
        content=question,
        meta={"language": language, "domain": domain},
    )
    append_message(
        conversation_id,
        role="assistant",
        content=answer,
        meta={
            "language": language,
            "domain": domain,
            "citations": citations,
            "live_sources": live_chunks,
            "context_notice": answer_scope_notice(language, sources, context_chunks, live_chunks),
        },
    )

    return {
        "conversation_id": conversation_id,
        "question": question,
        "domain": domain,
        "language": language,
        "context_sources": sources,
        "context_source_label": context_label,
        "context_notice": answer_scope_notice(language, sources, context_chunks, live_chunks),
        "domain_scores": scores,
        "answer": answer,
        "citations": citations,
        "live_sources": live_chunks,
    }


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run(
        app,
        host=host,
        port=int(os.getenv("PORT", "8000")),
        reload=False,
    )
