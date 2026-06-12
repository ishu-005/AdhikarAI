"""Groq chat model via LangChain, with a ranked fallback chain.

The available-model list is fetched from Groq at most once an hour (not on every
request, unlike the old `_call_groq`). Models are tried best-first; a failure on
one rolls to the next through LangChain's ``with_fallbacks``.
"""
from __future__ import annotations

import time

import requests
from langchain_core.runnables import Runnable

from backend.core.config import get_settings
from backend.core.logging import get_logger
from backend.core.metrics import metrics

logger = get_logger("llm")

_PREFERRED = [
    "llama-3.3-70b-versatile",
    "deepseek-r1-distill-llama-70b",
    "qwen-qwq-32b",
    "mixtral-8x7b-32768",
    "llama-3.1-70b-versatile",
    "llama-3.1-8b-instant",
]
_MODEL_CACHE: dict[str, object] = {"models": None, "fetched_at": 0.0}
_TTL = 3600


def _rank(models: list[str]) -> list[str]:
    rank = {name: i for i, name in enumerate(_PREFERRED)}
    return sorted(models, key=lambda m: rank.get(m, len(_PREFERRED) + 100))


def _available_models(api_key: str) -> set[str]:
    now = time.time()
    if _MODEL_CACHE["models"] is not None and now - float(_MODEL_CACHE["fetched_at"]) < _TTL:
        return _MODEL_CACHE["models"]  # type: ignore[return-value]
    try:
        resp = requests.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=12,
        )
        resp.raise_for_status()
        available = {item.get("id", "").strip() for item in (resp.json().get("data") or []) if item.get("id")}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not fetch Groq model list (%s); using configured chain.", exc)
        available = set()
    _MODEL_CACHE["models"] = available
    _MODEL_CACHE["fetched_at"] = now
    return available


def resolve_model_chain() -> list[str]:
    settings = get_settings()
    chain = settings.model_candidates
    available = _available_models(settings.groq_api_key) if settings.groq_api_key else set()
    if available:
        matched = [m for m in chain if m in available]
        extras = _rank([m for m in available if m not in matched])
        chain = matched + extras
    return chain or settings.model_candidates


def _make_chat(model: str):
    from langchain_groq import ChatGroq

    settings = get_settings()
    return ChatGroq(
        model=model,
        api_key=settings.groq_api_key,
        temperature=settings.groq_temperature,
        timeout=40,
        max_retries=0,
    )


def get_llm() -> Runnable:
    """Return a ChatGroq runnable with the rest of the chain as fallbacks."""
    chain = resolve_model_chain()
    primary_name = chain[0]
    metrics.set_model(primary_name)
    primary = _make_chat(primary_name)
    fallbacks = [_make_chat(m) for m in chain[1:]]
    return primary.with_fallbacks(fallbacks) if fallbacks else primary
