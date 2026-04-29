# AdhikarAI (RAG Legal Assistant)

FastAPI app for citizen legal guidance using:
- Domain detection
- Vector retrieval over ingested PDF/web content
- Live source snapshots from configured URLs
- LLM generation with fallback mode

## 1) Current Production Gaps (Now Addressed)

The following were missing and have now been implemented in code:
- Env-driven runtime settings for model, collection, upload and query limits
- Lazy embedding-model loading with a low-memory fallback so Windows can ingest without wiping Chroma data
- Startup initialization and readiness details in health endpoint
- Safer upload path handling with max file size validation
- Better error handling/logging for LLM fallback path
- Ingestor robustness for empty/corrupt hash files and missing YAML keys
- Scheduler interval from env and graceful shutdown handling

## 2) Recommended Free Deployable DB (Production)

Use PostgreSQL + `pgvector` on Supabase (free tier) or Neon (free tier).

Why this is the best next step for production:
- Fully managed and deployable (not local-only like persistent file storage)
- Standard SQL + metadata filtering + backups + observability
- Easy auth/network controls for secure deployments
- Cheap scale path from free tier to paid without rewriting your stack

Suggested architecture:
- Keep PostgreSQL as source of truth for users, audit logs, query logs, document metadata
- Store embeddings in `pgvector` table (or keep Chroma short-term and migrate gradually)

Alternative free vector DBs:
- Qdrant Cloud free tier (very good for vector-first workloads)
- Weaviate Cloud sandbox (for short-lived experimentation)

## 3) Environment Variables

Create a `.env` file (see `.env.example`):

- `ENV=dev`
- `PORT=8000`
- `LOG_LEVEL=INFO`
- `GROQ_API_KEY=`
- `GROQ_MODEL=llama-3.1-8b-instant`
- `GROQ_MODEL_FALLBACK=llama-3.1-8b-instant`
- `GROQ_MODELS=llama-3.3-70b-versatile,deepseek-r1-distill-llama-70b,qwen-qwq-32b,mixtral-8x7b-32768,llama-3.1-70b-versatile,llama-3.1-8b-instant`
- `RERANKER_ENABLED=true`
- `RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2`
- `EMBEDDING_MODEL=intfloat/multilingual-e5-large`
- `EMBEDDING_MODEL_FALLBACK=intfloat/multilingual-e5-small`
- `CHROMA_PATH=./chroma_store`
- `CHROMA_COLLECTION=lexrag`
- `MAX_QUERY_CHARS=4000`
- `UPLOAD_MAX_MB=20`
- `CRAWL_INTERVAL_HOURS=24`

## 4) Local Run

Install backend dependencies:

```bash
pip install -r backend/requirements.txt
```

Optional: download starter PDFs (from backend folder):

```bash
python backend/pdfDownload.py
```

Ingest PDFs and dynamic links:

```bash
python backend/ingestor.py
```

Run API/web app (start backend server):

```bash
python backend/app.py
```

This keeps the server tied to that terminal session. If you close/kill that terminal, the local server stops.

## 5) API Endpoints

- `GET /` UI page
- `GET /api/health` health + readiness flags
- `GET /api/sources` dynamic source config
- `GET /api/domains` normalized domain catalog used by UI and uploads
- `GET /api/pdf-status` discovered PDFs by domain
- `POST /api/upload-pdf` upload PDF by domain
- `POST /api/chat/new` create a new conversation thread
- `GET /api/chat/{conversation_id}` read stored thread messages
- `POST /api/query` ask question and retrieve response/citations

`/api/query` now accepts optional `conversation_id` to support multi-turn chat context.

## 6) Deploy Plan (Production Ready)

1. Deploy FastAPI app to Render, Railway, or Fly.io.
2. Use managed PostgreSQL (`pgvector`) on Supabase/Neon.
3. Keep ingestion as a separate worker process or scheduled job.
4. Add rate limit and auth at API gateway/reverse proxy.
5. Store secrets in platform secret manager (never in repo).
6. Add daily backup policy for DB and document sources.

Free deployment options:

1. Render free web service + cron job (simple setup, can sleep on free tier)
2. Railway hobby/free credits (easy env/secret management)
3. Fly.io starter credits (good for always-on container with volume)

Recommended free stack for this project:

1. App API: Render or Railway
2. Vector/metadata DB: Supabase Postgres + pgvector free tier
3. Object/file storage (optional): Supabase Storage free tier
4. Scheduled ingestion: platform cron or GitHub Actions schedule

## 7) PDF Folder Structure

Place PDFs under domain folders:

- `pdfs/criminal_law/`
- `pdfs/consumer/`
- `pdfs/labour/`
- `pdfs/rti/`
- `pdfs/human_rights/`
- Additional domain folders are supported and inferred from folder names.

## 8) Non-Destructive Ingestion Note

If the primary embedding model cannot load on your machine, the app falls back to `EMBEDDING_MODEL_FALLBACK` and writes to a versioned Chroma collection instead of deleting existing data. Your PDFs, source files, and existing `chroma_store` contents remain intact.

## 9) Robust PDF Downloading

`pdfDownload.py` now includes:

- strict PDF payload validation (blocks HTML/CSS/error pages)
- automatic scraping of candidate pages to discover real PDF links when direct URLs fail
- retry with backoff for transient failures
- quarantine of invalid existing files under `pdfs/_invalid/`
- machine-readable run report at `pdfs/download_report.json`

Useful environment controls:

- `PDF_DOWNLOAD_TIMEOUT`
- `PDF_DOWNLOAD_RETRIES`
- `PDF_DOWNLOAD_BACKOFF_SEC`
