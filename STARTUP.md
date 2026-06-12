# AdhikarAI — Quick Start Guide

The easiest way to run the entire project is with a single command.

## Prerequisites (one-time setup)

1. **Python 3.11+** installed
2. **Create `.env` file** from `.env.example`:
   ```bash
   copy .env.example .env
   ```
   Fill in your credentials:
   ```env
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_API_KEY=your_service_role_key
   GROQ_API_KEY=your_groq_key          # LLM (console.groq.com)
   COHERE_API_KEY=your_cohere_key      # embeddings + reranker (dashboard.cohere.com/api-keys)
   EMBEDDING_PROVIDER=cohere
   ```
   > Embeddings and reranking are cloud API calls — there are **no local models to
   > download**, so the app stays light enough for free 512MB hosts.

3. **Install Python dependencies** (one time):
   ```bash
   pip install -r requirements.txt
   ```

4. **Apply Supabase migration** (one time):
   - Go to Supabase Dashboard → SQL Editor
   - Copy-paste the entire contents of `supabase_migration.sql`
   - Click "Run"
   - Verify the final SELECT shows all `true`

## Run the Project

### Option 1: Backend only (data already ingested)
```bash
python run.py
```
or on Windows:
```batch
run.bat
```

Opens at **http://127.0.0.1:8000**

### Option 2: Download acts + ingest + backend
```bash
python run.py --download
```
or on Windows:
```batch
run.bat download
```

This downloads authoritative Indian bare acts from India Code, validates them, chunks by section, embeds, and stores in Supabase. Takes ~10–15 minutes.

### Option 3: Backend + frontend dev server (with hot reload)
```bash
python run.py --frontend
```
or on Windows:
```batch
run.bat frontend
```

Backend: **http://127.0.0.1:8000** (API only)  
Frontend: **http://localhost:3000** (with hot reload for development)

### Option 4: Everything (download, ingest, backend, frontend)
```bash
python run.py --full
```
or on Windows:
```batch
run.bat full
```

## What happens

The startup script (`run.py`) handles:

1. **Validation** — checks `.env`, Supabase connectivity
2. **Download** (optional) — fetches bare acts from India Code, validates PDF integrity
3. **Ingest** (optional) — chunks PDFs by legal section, embeds via Cohere `embed-multilingual-v3.0`, stores in Supabase
4. **Backend** — starts FastAPI on port 8000 (serves UI + API)
5. **Frontend** (optional) — starts Next.js dev server on port 3000

## Troubleshooting

### "Missing environment variables"
→ Check `.env` file has `SUPABASE_URL`, `SUPABASE_API_KEY`, `GROQ_API_KEY`

### "Supabase check failed"
→ Verify credentials are correct. Run the migration manually: Supabase Dashboard → SQL Editor → paste `supabase_migration.sql`

### "Backend failed to start"
→ Port 8000 already in use. Change with:
```bash
python run.py --port 8001
```

### "Frontend npm not found"
→ Install Node.js from https://nodejs.org (includes npm)

### "Download timeout"
→ India Code servers are slow. Re-run `python run.py --download` — it retries with backoff

## Next steps

Once running:

1. **Ask a legal question** in English or Hindi
2. **Watch streaming** — token-by-token response generation
3. **See citations** — each chunk is cited by legal section, source, and confidence
4. **Upload PDFs** — auto-ingested into the corpus
5. **Check metrics** — `/api/metrics` shows latency, cache hit-rate, model used

---

For detailed architecture, see `README.md` and `DEPLOY.md`.
