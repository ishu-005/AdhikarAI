# Deploying AdhikarAI for Free

Recommended split deploy — **frontend on Vercel, backend on Render**:

| Piece | Free service | Notes |
|---|---|---|
| Frontend (Next.js UI) | **Vercel** | native Next build, global CDN, auto-deploy on push |
| Backend (FastAPI) | **Render** | native Python web service, ~300MB, fits free 512MB |
| Vector DB | **Supabase** | pgvector + Postgres, 500 MB DB |
| LLM | **Groq** | OpenAI-compatible, fast |
| Embeddings + reranker | **Cohere** (trial) / **Jina** | cloud calls — no local ML models |

Because embeddings/reranking are cloud API calls (no `torch`/`sentence-transformers`),
the backend stays light enough for Render's free tier.

> Single-container alternative (FastAPI serves the UI on one host, e.g. Hugging Face
> Spaces) is still supported — see the bottom of this doc.

---

## 1. Supabase (free)

1. Create a project at https://supabase.com.
2. SQL Editor → paste **`supabase_migration.sql`** → Run. Confirm the verification
   rows at the bottom are all `true` (incl. `fulltext search function` and `chats table`).
3. Settings → API → copy the **Project URL** and the **service_role** key
   (RLS restricts writes to that role).

## 2. API keys

- **Groq** — https://console.groq.com → `gsk_...` (LLM only).
- **Cohere** — https://dashboard.cohere.com/api-keys (free trial, no card):
  `embed-multilingual-v3.0` + `rerank-multilingual-v3.0`.
- **Jina** (optional alternative) — https://jina.ai → API Keys (1M tokens free).

> **Embedding provider is fixed.** Documents and queries must use the *same* provider
> (different providers = different vector spaces). To switch `EMBEDDING_PROVIDER`, wipe
> `legal_documents` and re-ingest.

## 3. Load data (one-time, from your machine)

```bash
pip install -r requirements.txt
python ingestor.py            # chunks pdfs/**, embeds via Cohere, stores in Supabase
```
On a Cohere **trial** key the first full ingest is rate-paced (~10 min, one-time);
queries are unaffected. Uploaded PDFs (via the UI) are auto-ingested afterwards.

---

## 4. Backend → Render

1. Push this repo to GitHub.
2. Render Dashboard → **New → Blueprint** → pick this repo. It reads
   [`render.yaml`](render.yaml) (native Python, `uvicorn` on `$PORT`, health check at
   `/api/health`).
3. When prompted, fill the secret env vars (they are `sync:false` in the blueprint):
   `SUPABASE_URL`, `SUPABASE_API_KEY`, `GROQ_API_KEY`, `COHERE_API_KEY`,
   `JINA_API_KEY` (optional). Leave `ALLOWED_ORIGINS` for now (step 6).
4. Deploy. Note the service URL, e.g. `https://adhikarai-api.onrender.com`.
5. Verify: open `https://adhikarai-api.onrender.com/api/health` → `vector_store_ready: true`.

> Render's free tier **sleeps after 15 min idle**; the next request cold-starts in
> ~50s. Fine for a demo. For always-on free, Koyeb/Fly.io are alternatives.

## 5. Frontend → Vercel

1. Vercel → **Add New → Project** → import this repo.
2. Set **Root Directory** = `frontend-next` (Vercel auto-detects Next.js).
3. Add an environment variable:
   - `NEXT_PUBLIC_API_BASE` = your Render URL (no trailing slash), e.g.
     `https://adhikarai-api.onrender.com`
4. Deploy. Note the Vercel URL, e.g. `https://adhikarai.vercel.app`.

## 6. Wire CORS (connect the two)

1. Back in Render → your service → **Environment** → set
   `ALLOWED_ORIGINS` = your Vercel URL, e.g. `https://adhikarai.vercel.app`.
   (Vercel *preview* URLs are already allowed via the built-in `*.vercel.app` regex.)
2. Render redeploys. Open the Vercel URL and ask a question — done. 🎉

---

## Local development

```bash
# Terminal 1 — backend
python run.py                 # http://localhost:8000  (auto-bumps port if busy)

# Terminal 2 — UI (proxies /api to the backend via .env.local)
cd frontend-next
npm install
npm run dev                   # http://localhost:3000
```
`frontend-next/.env.local` sets `NEXT_PUBLIC_API_BASE=http://localhost:8000`.

## Single-container alternative (one host serves UI + API)

Build the UI as a static export and let FastAPI serve it:

```bash
cd frontend-next && npm run build:static   # writes frontend-next/out
cd .. && python run.py                       # UI now at http://localhost:8000
```
The [`Dockerfile`](Dockerfile) does exactly this (`STATIC_EXPORT=true`) for Hugging
Face Spaces / any Docker host on port 7860.
