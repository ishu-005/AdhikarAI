"""Central application settings.

All tunable behavior is driven by environment variables (loaded from `.env`).
This replaces the inline `Settings` class that used to live in `backend/app.py`.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

# Repository root (…/AdhikarAI). `__file__` is …/backend/core/config.py
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = Path(__file__).resolve().parents[1]


def resolve_path(*parts: str, base: Path = PROJECT_ROOT) -> Path:
    """Resolve a path relative to the project root (CWD-independent)."""
    return base.joinpath(*parts)


class Settings(BaseModel):
    # ── Collection / embeddings ────────────────────────────────────────
    collection_name: str = os.getenv("COLLECTION_NAME", "legal_documents")
    embedding_dimension: int = int(os.getenv("EMBEDDING_DIMENSION", "1024"))
    # The embedding provider is FIXED for both ingest and query — the two must
    # match or cosine similarity is meaningless (different providers ≠ same vector
    # space). One of: cohere | jina | hashing. No silent cross-provider fallback.
    embedding_provider: str = os.getenv("EMBEDDING_PROVIDER", "cohere").strip().lower()
    cohere_api_key: str = os.getenv("COHERE_API_KEY", "").strip()
    cohere_embed_model: str = os.getenv("COHERE_EMBED_MODEL", "embed-multilingual-v3.0")
    cohere_rerank_model: str = os.getenv("COHERE_RERANK_MODEL", "rerank-multilingual-v3.0")
    jina_api_key: str = os.getenv("JINA_API_KEY", "").strip()
    jina_embed_model: str = os.getenv("JINA_EMBED_MODEL", "jina-embeddings-v3")

    # ── Groq LLM ───────────────────────────────────────────────────────
    groq_api_key: str = os.getenv("GROQ_API_KEY", "").strip()
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    groq_model_fallback: str = os.getenv("GROQ_MODEL_FALLBACK", "llama-3.1-8b-instant")
    groq_models: str = os.getenv("GROQ_MODELS", "").strip()
    groq_temperature: float = float(os.getenv("GROQ_TEMPERATURE", "0.2"))

    # ── Retrieval ──────────────────────────────────────────────────────
    top_k: int = int(os.getenv("TOP_K", "5"))
    retrieve_multiplier: int = int(os.getenv("RETRIEVE_MULTIPLIER", "3"))
    rerank_top_n: int = int(os.getenv("RERANK_TOP_N", "5"))
    reranker_model: str = os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
    reranker_enabled: bool = os.getenv("RERANKER_ENABLED", "true").lower() == "true"
    hybrid_enabled: bool = os.getenv("HYBRID_ENABLED", "true").lower() == "true"
    vector_weight: float = float(os.getenv("VECTOR_WEIGHT", "0.6"))
    fulltext_weight: float = float(os.getenv("FULLTEXT_WEIGHT", "0.4"))
    # Legacy broad retrieval flag. Domain-profile retrieval passes scoped=True
    # and is always filtered to the profile's target domain.
    retrieval_domain_filter: bool = os.getenv("RETRIEVAL_DOMAIN_FILTER", "false").lower() == "true"

    # ── Request limits / CORS ──────────────────────────────────────────
    max_query_chars: int = int(os.getenv("MAX_QUERY_CHARS", "4000"))
    upload_max_mb: int = int(os.getenv("UPLOAD_MAX_MB", "20"))
    allowed_origins: str = os.getenv("ALLOWED_ORIGINS", "*")
    # Regex for CORS (e.g. Vercel preview URLs). Default matches any *.vercel.app.
    allowed_origin_regex: str = os.getenv("ALLOWED_ORIGIN_REGEX", r"https://.*\.vercel\.app")
    allowed_upload_domains: str = os.getenv(
        "ALLOWED_UPLOAD_DOMAINS",
        "criminal_law,consumer,labour,rti,human_rights,citizen_rights,"
        "women_family,property_finance,case_law,legislation,grievance",
    )

    # ── Supabase ───────────────────────────────────────────────────────
    use_supabase: bool = os.getenv("USE_SUPABASE", "true").lower() == "true"
    supabase_url: str = os.getenv("SUPABASE_URL", "").strip()
    supabase_api_key: str = os.getenv("SUPABASE_API_KEY", "").strip()
    supabase_bucket_name: str = os.getenv("SUPABASE_BUCKET_NAME", "pdfs")

    # ── Cache / misc ───────────────────────────────────────────────────
    cache_ttl_seconds: int = int(os.getenv("CACHE_TTL_SECONDS", "1800"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()

    @property
    def model_candidates(self) -> list[str]:
        """Ordered, de-duplicated Groq model fallback chain."""
        explicit = [m.strip() for m in self.groq_models.split(",") if m.strip()]
        default_chain = [
            "llama-3.3-70b-versatile",
            "deepseek-r1-distill-llama-70b",
            "qwen-qwq-32b",
            "mixtral-8x7b-32768",
            "llama-3.1-70b-versatile",
            "llama-3.1-8b-instant",
        ]
        ordered = explicit or [self.groq_model, self.groq_model_fallback] + default_chain
        seen: set[str] = set()
        result: list[str] = []
        for m in ordered:
            if m and m not in seen:
                seen.add(m)
                result.append(m)
        return result

    @property
    def allowed_domains(self) -> set[str]:
        return {d.strip().lower() for d in self.allowed_upload_domains.split(",") if d.strip()}

    @property
    def cors_origins(self) -> list[str]:
        origins = [o.strip() for o in self.allowed_origins.split(",") if o.strip()]
        return origins or ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
