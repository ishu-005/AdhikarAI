"""Cloud embeddings with automatic fallback.

Priority: Cohere embed-multilingual-v3.0 → Jina jina-embeddings-v3 → HashingEmbedder.
No local model downloads required.
"""
from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache

import requests as _requests
from langchain_core.embeddings import Embeddings

from backend.core.config import get_settings
from backend.core.logging import get_logger

logger = get_logger("embeddings")


class HashingEmbedder(Embeddings):
    """Deterministic, zero-dependency fallback (MD5 bag-of-words, L2-normalised)."""

    def __init__(self, dimension: int = 1024) -> None:
        self.dimension = dimension

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in re.findall(r"[a-z0-9]+", (text or "").lower()):
            slot = int.from_bytes(hashlib.md5(token.encode()).digest()[:4], "big") % self.dimension
            vector[slot] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)


class JinaEmbedder(Embeddings):
    """Jina AI REST embeddings — jina-embeddings-v3, 1024-dim, 1M tokens free."""

    def __init__(self, api_key: str, model: str = "jina-embeddings-v3") -> None:
        self._api_key = api_key
        self._model = model
        self._url = "https://api.jina.ai/v1/embeddings"

    def _call(self, texts: list[str], task: str) -> list[list[float]]:
        resp = _requests.post(
            self._url,
            headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
            json={"input": texts, "model": self._model, "task": task},
            timeout=30,
        )
        resp.raise_for_status()
        return [d["embedding"] for d in resp.json()["data"]]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._call(texts, "retrieval.passage")

    def embed_query(self, text: str) -> list[float]:
        return self._call([text], "retrieval.query")[0]


def normalize_embedding(vector: list[float], target_dimension: int = 1024) -> list[float]:
    if len(vector) == target_dimension:
        return vector
    if len(vector) > target_dimension:
        return vector[:target_dimension]
    return vector + [0.0] * (target_dimension - len(vector))


@lru_cache
def get_embedding_stack() -> tuple[str, Embeddings]:
    """Return (model_name, Embeddings) for the FIXED configured provider.

    There is intentionally no cross-provider fallback: documents and queries must
    be embedded by the same provider, or retrieval silently returns nonsense.
    Switching EMBEDDING_PROVIDER therefore requires re-ingesting the corpus.
    """
    settings = get_settings()
    provider = settings.embedding_provider

    if provider == "cohere":
        if not settings.cohere_api_key:
            raise RuntimeError(
                "EMBEDDING_PROVIDER=cohere but COHERE_API_KEY is not set. "
                "Add the key to .env (dashboard.cohere.com/api-keys) or switch EMBEDDING_PROVIDER."
            )
        from langchain_cohere import CohereEmbeddings

        embedder = CohereEmbeddings(
            cohere_api_key=settings.cohere_api_key,
            model=settings.cohere_embed_model,
        )
        logger.info("Embedding provider: Cohere %s", settings.cohere_embed_model)
        return settings.cohere_embed_model, embedder

    if provider == "jina":
        if not settings.jina_api_key:
            raise RuntimeError(
                "EMBEDDING_PROVIDER=jina but JINA_API_KEY is not set. "
                "Add the key to .env (jina.ai → API Keys) or switch EMBEDDING_PROVIDER."
            )
        embedder = JinaEmbedder(settings.jina_api_key, settings.jina_embed_model)
        logger.info("Embedding provider: Jina %s", settings.jina_embed_model)
        return settings.jina_embed_model, embedder

    if provider == "hashing":
        logger.warning("Embedding provider: HashingEmbedder (offline, low quality).")
        return "hashing-1024-v1", HashingEmbedder(settings.embedding_dimension)

    raise RuntimeError(
        f"Unknown EMBEDDING_PROVIDER={provider!r}. Use one of: cohere | jina | hashing."
    )


def get_embeddings() -> Embeddings:
    return get_embedding_stack()[1]


def get_embedding_model_name() -> str:
    return get_embedding_stack()[0]
