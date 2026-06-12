---
title: AdhikarAI
sdk: docker
app_port: 7860
emoji: 🤖
colorFrom: blue
colorTo: green
short_description: RAG legal assistant for citizen rights guidance
---

# AdhikarAI

AdhikarAI is a legal help assistant for Indian citizen-rights questions. It reads legal PDFs and web sources, stores embeddings in Supabase using `pgvector`, and answers questions with retrieved context plus an LLM.

## What it does

- Ingests legal PDFs and source pages
- Splits them into searchable chunks
- Stores 1024-dim embeddings in Supabase
- Retrieves the best matches for a question
- Generates a plain-language answer with citations and source context

## How the workflow works

1. `ingestor.py` reads PDFs and configured web sources.
2. It generates embeddings and writes them into Supabase.
3. `backend/app.py` receives user questions from the UI.
4. The backend embeds the question and runs Supabase vector search.
5. The retrieved context is passed to the LLM, which writes the final answer.

## Setup

Create a `.env` file with at least these values:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_API_KEY=your_service_role_or_insert_key
GROQ_API_KEY=your_groq_key              # LLM only
EMBEDDING_PROVIDER=cohere               # cohere | jina | hashing
COHERE_API_KEY=your_cohere_key          # embeddings + reranker (cloud, no local model)
USE_SUPABASE=true
```

Embeddings and reranking are cloud API calls (Cohere/Jina) — there are no local ML
models, so the app runs in ~512MB and the Docker image is ~300MB. The provider is
fixed for both ingest and query; changing it requires re-ingesting the corpus.

If you are running locally on Windows, use the project virtual environment before running any commands.

## Run it locally

Install dependencies:

```bash
pip install -r requirements.txt
```

Download the bare-act corpus (validated PDFs from India Code) and run ingestion:

```bash
python -m backend.ingest.download   # fetch missing acts, validate, write pdfs/download_report.json
python ingestor.py                  # chunk by section, embed, store in Supabase
```

Every downloaded file is verified to be a real PDF (not an HTML error page), to
match the official act citation (year + act number), and to contain the act's
title text — invalid files are never written into `pdfs/`.

Build the UI once (FastAPI serves the static export at `/`):

```bash
cd frontend-next
npm install && npm run build
cd ..
```

Start the backend:

```bash
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8010
```

Open the app in your browser at:

```text
http://127.0.0.1:8010
```

For UI development with hot reload, run `npm run dev` inside `frontend-next/`
(set `NEXT_PUBLIC_API_BASE` in `frontend-next/.env.local`, see the example file).

## Free deployment

See `DEPLOY.md` — the whole stack runs free on Hugging Face Spaces (Docker, one
container serving API + UI), Supabase free tier (pgvector), and the Groq free API.

## Supabase migration

The repository uses Supabase as the vector store. Before running ingestion, make sure the Supabase SQL migration has been applied so `legal_documents.embedding` is `vector(1024)` and the `search_legal_documents` RPC exists.

## Project layout

- `backend/core/` - settings, Supabase client, logging, metrics, text/domain helpers
- `backend/rag/` - LangChain RAG core (embeddings, hybrid retriever, LLM, LCEL chain, pipeline)
- `backend/ingest/` - PDF parsing, embed+store, scheduled web crawl
- `backend/app.py` - thin FastAPI route layer
- `frontend-next/` - Next.js / React UI (compiled to a static export served by FastAPI)
- `frontend/` - legacy vanilla-JS UI (fallback if the Next export is absent)
- `ingestor.py` - ingestion entrypoint (delegates to `backend/ingest`)
- `supabase_migration.sql` - **the** schema/migration file (vector + full-text RPCs, chat tables)
- `eval/` - offline RAG evaluation harness (`run_eval.py`, `golden.yaml`)
- `DEPLOY.md` - free-tier deployment guide; `QUICKSTART.md` - migration notes

## Useful endpoints

- `GET /` - UI
- `GET /api/health` - health and readiness (pings Supabase)
- `GET /api/metrics` - latency percentiles, cache hit-rate, last model used
- `GET /api/domains` - supported domain list
- `GET /api/sources` - configured dynamic sources
- `POST /api/query` - ask a legal question (JSON response)
- `POST /api/query/stream` - ask a legal question (SSE token stream)
- `POST /api/upload-pdf` - upload a PDF (auto-ingested in the background)

## Notes

- The embedding model can take a while to load the first time.
- If the model is unavailable, the app falls back to a smaller option.
- Uploaded and ingested content is stored in Supabase, so it survives app restarts.

## If something looks off

- Check `.env` for `SUPABASE_URL`, `SUPABASE_API_KEY`, and `GROQ_API_KEY`.
- Re-run the Supabase migration if the vector search RPC or embedding column is missing.
- If ingestion fails, run it once in the terminal and read the exact error before changing anything else.
