"""Hybrid retrieval: pgvector similarity + Postgres full-text, fused and reranked.

This replaces the old `vector_retrieve` (and its broken `_rerank_results` path).
Retrievers are built per-request with the target domain baked in; the heavy models
(embeddings, cross-encoder) are cached, so construction is cheap.
"""
from __future__ import annotations

from functools import lru_cache

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from backend.core.clients import get_supabase_client
from backend.core.config import get_settings
from backend.core.logging import get_logger
from backend.rag.embeddings import get_embeddings, normalize_embedding

logger = get_logger("retriever")


def _row_to_doc(row: dict) -> Document:
    return Document(
        page_content=row.get("content", "") or "",
        metadata={
            "domain": row.get("domain", "general"),
            "source": row.get("source", "database"),
            "title": row.get("title", ""),
            "metadata": row.get("metadata") or {},
            "similarity": float(row.get("similarity", row.get("rank", 0)) or 0),
        },
    )


class _SupabaseVectorRetriever(BaseRetriever):
    """Vector similarity via the `search_legal_documents` RPC."""

    domain: str = "general"
    match_count: int = 10

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        client = get_supabase_client()
        if client is None:
            return []
        vector = get_embeddings().embed_query(query)
        vector = normalize_embedding(list(vector), get_settings().embedding_dimension)
        try:
            resp = client.rpc(
                "search_legal_documents",
                {"query_embedding": vector, "search_domain": self.domain, "match_count": self.match_count},
            ).execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Vector RPC failed: %s", exc)
            return []
        return [_row_to_doc(r) for r in (resp.data or [])]


class _SupabaseFullTextRetriever(BaseRetriever):
    """Keyword search via the `fulltext_search_legal_documents` RPC (ts_rank)."""

    domain: str = "general"
    match_count: int = 10

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        client = get_supabase_client()
        if client is None:
            return []
        try:
            resp = client.rpc(
                "fulltext_search_legal_documents",
                {"query_text": query, "search_domain": self.domain, "match_count": self.match_count},
            ).execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Full-text RPC unavailable (%s); skipping keyword retrieval.", exc)
            return []
        return [_row_to_doc(r) for r in (resp.data or [])]


def _doc_identity(doc: Document) -> tuple[str, str, str]:
    metadata = doc.metadata or {}
    stored = metadata.get("metadata") if isinstance(metadata.get("metadata"), dict) else {}
    source = str(stored.get("filename") or metadata.get("source") or "")
    title = str(stored.get("title") or metadata.get("title") or "")
    content = " ".join((doc.page_content or "").split())[:500]
    return source, title, content


def _fuse_documents(
    vector_docs: list[Document],
    fulltext_docs: list[Document],
    *,
    vector_weight: float,
    fulltext_weight: float,
) -> list[Document]:
    """Merge vector and keyword results without depending on LangChain extras."""
    scored: dict[tuple[str, str, str], tuple[float, int, Document]] = {}
    sequence = 0
    for docs, weight in ((vector_docs, vector_weight), (fulltext_docs, fulltext_weight)):
        for rank, doc in enumerate(docs):
            key = _doc_identity(doc)
            # Reciprocal-rank fusion keeps keyword-only exact section hits visible
            # even when their numeric rank field is missing or incomparable.
            score = weight / (rank + 1)
            if key in scored:
                previous_score, first_seen, existing = scored[key]
                scored[key] = (previous_score + score, first_seen, existing)
            else:
                scored[key] = (score, sequence, doc)
                sequence += 1
    return [item[2] for item in sorted(scored.values(), key=lambda item: (-item[0], item[1]))]


class _HybridRetriever(BaseRetriever):
    """Local vector + full-text retriever that works without optional LangChain modules."""

    vector: BaseRetriever
    fulltext: BaseRetriever
    vector_weight: float = 0.6
    fulltext_weight: float = 0.4

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        vector_docs = self.vector.invoke(query)
        fulltext_docs = self.fulltext.invoke(query)
        return _fuse_documents(
            vector_docs,
            fulltext_docs,
            vector_weight=self.vector_weight,
            fulltext_weight=self.fulltext_weight,
        )


@lru_cache
def _get_reranker():
    settings = get_settings()
    if not settings.reranker_enabled or not settings.cohere_api_key:
        return None
    try:
        from langchain_cohere import CohereRerank

        reranker = CohereRerank(
            cohere_api_key=settings.cohere_api_key,
            model=settings.cohere_rerank_model,
            top_n=settings.rerank_top_n,
        )
        logger.info("Reranker: Cohere %s", settings.cohere_rerank_model)
        return reranker
    except Exception as exc:  # noqa: BLE001
        logger.warning("Cohere reranker unavailable (%s); skipping reranking.", exc)
        return None


def build_retriever(domain: str, scoped: bool = False) -> BaseRetriever:
    """Compose vector (+ full-text) retrieval, fused and optionally reranked."""
    settings = get_settings()
    pool = settings.top_k * settings.retrieve_multiplier
    # Search the whole corpus unless domain filtering is explicitly enabled —
    # avoids misses when the router domain != a doc's stored folder-domain.
    search_domain = domain if scoped or settings.retrieval_domain_filter else "general"

    vector = _SupabaseVectorRetriever(domain=search_domain, match_count=pool)
    base: BaseRetriever = vector

    if settings.hybrid_enabled:
        fulltext = _SupabaseFullTextRetriever(domain=search_domain, match_count=pool)
        base = _HybridRetriever(
            vector=vector,
            fulltext=fulltext,
            vector_weight=settings.vector_weight,
            fulltext_weight=settings.fulltext_weight,
        )

    reranker = _get_reranker()
    if reranker is not None:
        try:
            from langchain.retrievers import ContextualCompressionRetriever

            return ContextualCompressionRetriever(
                base_compressor=reranker, base_retriever=base
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Reranker wiring failed (%s); returning fused results.", exc)

    return base


def retrieve(question: str, domain: str, scoped: bool = False) -> list[Document]:
    """Run retrieval and return ranked documents (best-effort, never raises)."""
    try:
        docs = build_retriever(domain, scoped=scoped).invoke(question)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Retrieval failed: %s", exc)
        return []
    return docs[: get_settings().top_k]
