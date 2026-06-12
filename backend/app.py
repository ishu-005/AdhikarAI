"""AdhikarAI FastAPI app — thin route layer over backend/core + backend/rag + backend/ingest."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import uvicorn
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from backend.core import chat_store
from backend.core.cache import OptimizationCache
from backend.core.clients import get_supabase_client
from backend.core.config import PROJECT_ROOT, get_settings
from backend.core.logging import RequestIDMiddleware, configure_logging, get_logger
from backend.core.metrics import metrics
from backend.core.sse import cached_stream_events, sse
from backend.core.text import (
    detect_domain,
    detect_language,
    get_domain_catalog,
    load_links_config,
    normalize_domain,
    normalize_text,
)
from backend.core.chat_intelligence import rewrite_followup
from backend.ingest.pdf import ingest_pdf_bytes
from backend.rag import pipeline

logger = get_logger("app")
settings = get_settings()
opt_cache = OptimizationCache(ttl_seconds=settings.cache_ttl_seconds)

FRONTEND_DIR = PROJECT_ROOT / "frontend"
# Next.js static export written by `npm run build` (output: 'export' -> ./out).
# Absent during local dev (UI runs on :3000); FastAPI then just serves the API.
NEXT_EXPORT_DIR = PROJECT_ROOT / "frontend-next" / "out"


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    if settings.use_supabase:
        loaded = chat_store.load_all_from_supabase()
        logger.info("Loaded %d chats from Supabase.", loaded)
    yield


app = FastAPI(title="AdhikarAI RAG API", version="2.0.0", lifespan=lifespan)
app.add_middleware(RequestIDMiddleware)

# CORS: a wildcard cannot be combined with credentials (browsers reject it).
# With explicit origins (e.g. the Vercel domain) credentials are allowed, plus
# an origin regex so Vercel preview deployments work without listing each URL.
_cors: dict = {"allow_methods": ["*"], "allow_headers": ["*"]}
if settings.cors_origins == ["*"]:
    _cors.update(allow_origins=["*"], allow_credentials=False)
else:
    _cors.update(allow_origins=settings.cors_origins, allow_credentials=True)
    if settings.allowed_origin_regex:
        _cors["allow_origin_regex"] = settings.allowed_origin_regex
app.add_middleware(CORSMiddleware, **_cors)

# Legacy Jinja UI is optional; the Next.js export is the canonical front end.
_LEGACY_STATIC = FRONTEND_DIR / "static"
if _LEGACY_STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(_LEGACY_STATIC)), name="static")
if (NEXT_EXPORT_DIR / "_next").exists():
    app.mount("/_next", StaticFiles(directory=str(NEXT_EXPORT_DIR / "_next")), name="next-assets")
_LEGACY_TEMPLATES = FRONTEND_DIR / "templates"
templates = (
    Jinja2Templates(directory=str(_LEGACY_TEMPLATES)) if _LEGACY_TEMPLATES.exists() else None
)


# ── Models ─────────────────────────────────────────────────────────────
class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=settings.max_query_chars)
    language: str | None = None
    conversation_id: str | None = None


class RenameRequest(BaseModel):
    name: str


# ── Pages ──────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    next_index = NEXT_EXPORT_DIR / "index.html"
    if next_index.exists():
        return HTMLResponse(next_index.read_text(encoding="utf-8"))
    if templates is not None:
        return templates.TemplateResponse(request=request, name="index.html")
    return HTMLResponse(
        "<h1>AdhikarAI API is running</h1>"
        "<p>The UI is not built. Run <code>cd frontend-next &amp;&amp; npm run dev</code> "
        "for development, or <code>npm run build</code> to serve it from here. "
        "API docs at <a href='/docs'>/docs</a>.</p>"
    )


# ── Meta endpoints ─────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    client = get_supabase_client()
    vector_ready = False
    if client is not None:
        try:
            client.table("legal_documents").select("id").limit(1).execute()
            vector_ready = True
        except Exception:  # noqa: BLE001
            vector_ready = False
    return {
        "status": "ok",
        "time": datetime.now(UTC).isoformat(),
        "supabase_configured": client is not None,
        "vector_store_ready": vector_ready,
    }


@app.get("/api/metrics")
async def get_metrics():
    return metrics.snapshot()


@app.get("/api/sources")
async def sources():
    return {"dynamic_sources": load_links_config()}


@app.get("/api/domains")
async def domains():
    return {"domains": get_domain_catalog()}


@app.get("/api/chats")
async def list_chats():
    return {"chats": chat_store.list_conversations()}


# ── Chat management ────────────────────────────────────────────────────
@app.post("/api/chat/new")
async def new_chat():
    return {"conversation_id": chat_store.create_conversation(), "messages": []}


@app.get("/api/chat/{conversation_id}")
async def read_chat(conversation_id: str):
    return {"conversation_id": conversation_id, "messages": chat_store.get_conversation(conversation_id)}


@app.delete("/api/chat/{conversation_id}")
async def delete_chat(conversation_id: str):
    chat_store.delete_conversation(conversation_id)
    return {"status": "deleted", "conversation_id": conversation_id}


@app.put("/api/chat/{conversation_id}/name")
async def rename_chat(conversation_id: str, request: RenameRequest):
    name = (request.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name cannot be empty")
    chat_store.rename_conversation(conversation_id, name)
    return {"status": "renamed", "conversation_id": conversation_id, "name": name}


# ── PDFs ───────────────────────────────────────────────────────────────
@app.get("/api/pdf-status")
async def pdf_status():
    root = PROJECT_ROOT / "pdfs"
    status = []
    for domain in get_domain_catalog():
        folder = root / domain
        files = sorted(p.name for p in folder.glob("*.pdf")) if folder.exists() else []
        status.append(
            {"domain": domain, "folder": str(folder).replace("\\", "/"), "pdf_count": len(files), "pdf_files": files}
        )
    return {"pdf_status": status}


def _ingest_pdf_background(data: bytes, filename: str, domain: str) -> None:
    try:
        stored = ingest_pdf_bytes(data, filename, domain)
        logger.info("Auto-ingested %s -> %d chunks.", filename, stored)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Auto-ingest failed for %s: %s", filename, exc)


@app.post("/api/upload-pdf")
async def upload_pdf(background: BackgroundTasks, domain: str = Form(...), pdf: UploadFile = File(...)):
    safe_domain = normalize_domain(domain)
    if not safe_domain or safe_domain in {"_invalid", ".", ".."}:
        raise HTTPException(status_code=400, detail="invalid domain")
    if safe_domain not in settings.allowed_domains:
        raise HTTPException(status_code=400, detail="domain not allowed")
    if not pdf.filename or not pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="only .pdf files are allowed")

    data = await pdf.read()
    if len(data) > settings.upload_max_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"file too large, max {settings.upload_max_mb} MB")

    folder = PROJECT_ROOT / "pdfs" / safe_domain
    folder.mkdir(parents=True, exist_ok=True)
    filename = Path(pdf.filename).name
    target = folder / filename
    target.write_bytes(data)

    # Auto-ingest so the upload is searchable without a manual ingestor run.
    background.add_task(_ingest_pdf_background, data, filename, safe_domain)

    return {
        "message": "pdf uploaded",
        "domain": safe_domain,
        "filename": filename,
        "saved_to": str(target).replace("\\", "/"),
        "size_bytes": len(data),
        "ingest_status": "queued",
    }


# ── Query (sync + streaming) ───────────────────────────────────────────
def _resolve_base(payload: QueryRequest) -> tuple[str, str, str]:
    question = normalize_text(payload.question)
    if not question:
        raise HTTPException(status_code=400, detail="question is required")
    if len(question) > settings.max_query_chars:
        raise HTTPException(status_code=400, detail="question exceeds max size")
    requested = (payload.language or "").strip().lower()
    language = requested if requested in {"en", "hi"} else detect_language(question)
    conversation_id = normalize_text(payload.conversation_id or "") or chat_store.create_conversation()
    return question, language, conversation_id


def _prepare_query(payload: QueryRequest) -> tuple[str, str, str, str, str, list[dict], bool]:
    original_question, language, conversation_id = _resolve_base(payload)
    history = chat_store.get_conversation(conversation_id)
    rewrite = rewrite_followup(original_question, history, language)
    if rewrite.rewritten:
        metrics.incr("query_rewritten")
    effective_question = rewrite.question
    domain, _ = detect_domain(effective_question)
    return original_question, effective_question, domain, language, conversation_id, history, rewrite.rewritten


@app.post("/api/query")
async def query(payload: QueryRequest):
    metrics.incr("query_total")
    original_question, question, domain, language, conversation_id, history, rewritten = _prepare_query(payload)
    _, scores = detect_domain(question)

    cached = opt_cache.get(question, domain, language)
    if cached:
        metrics.incr("cache_hit")
        result = cached
    else:
        result = await _run_in_thread(question, domain, language, history)
        opt_cache.set(question, domain, language, result)

    _append_chat_result(conversation_id, original_question, question, domain, language, result, rewritten)
    return {
        "conversation_id": conversation_id,
        "question": original_question,
        "effective_question": question,
        "domain": domain,
        "language": language,
        "domain_scores": scores,
        "_cached": bool(cached),
        "_rewritten": rewritten,
        **result,
    }


async def _run_in_thread(question: str, domain: str, language: str, history: list[dict]) -> dict:
    import anyio

    return await anyio.to_thread.run_sync(pipeline.answer_query, question, domain, language, history)


@app.post("/api/query/stream")
async def query_stream(payload: QueryRequest):
    metrics.incr("query_total")
    original_question, question, domain, language, conversation_id, history, rewritten = _prepare_query(payload)
    cached = opt_cache.get(question, domain, language)

    async def event_gen():
        if cached:
            metrics.incr("cache_hit")
            metrics.incr("stream_cache_hit")
            for event in cached_stream_events(conversation_id, domain, language, cached):
                yield event
            _append_chat_result(conversation_id, original_question, question, domain, language, cached, rewritten)
            return

        yield _sse(
            "meta",
            {"conversation_id": conversation_id, "domain": domain, "language": language, "_rewritten": rewritten},
        )
        final: dict = {}
        try:
            async for event in pipeline.astream_query(question, domain, language, history):
                if event["type"] == "token":
                    yield _sse("token", {"value": event["value"]})
                elif event["type"] == "replace":
                    yield _sse("replace", {"value": event["value"]})
                elif event["type"] == "done":
                    final = event
                    yield _sse("done", {k: v for k, v in event.items() if k != "type"})
        except Exception as exc:  # noqa: BLE001
            logger.exception("Stream failed: %s", exc)
            yield _sse("error", {"message": str(exc)})

        answer = final.get("answer", "")
        if answer:
            result = {k: final.get(k) for k in (
                "answer", "context_sources", "context_source_label", "context_notice", "citations", "live_sources"
            )}
            opt_cache.set(question, domain, language, result)
            _append_chat_result(conversation_id, original_question, question, domain, language, result, rewritten)

    return StreamingResponse(event_gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _sse(event: str, data: dict) -> str:
    return sse(event, data)


def _append_chat_result(
    conversation_id: str,
    original_question: str,
    effective_question: str,
    domain: str,
    language: str,
    result: dict,
    rewritten: bool,
) -> None:
    chat_store.append_message(
        conversation_id,
        "user",
        original_question,
        {"language": language, "domain": domain, "effective_question": effective_question, "rewritten": rewritten},
    )
    chat_store.append_message(
        conversation_id,
        "assistant",
        result.get("answer", ""),
        {
            "language": language,
            "domain": domain,
            "citations": result.get("citations", []),
            "live_sources": result.get("live_sources", []),
            "context_notice": result.get("context_notice", ""),
        },
    )


if __name__ == "__main__":
    uvicorn.run(app, host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8000")), reload=False)
