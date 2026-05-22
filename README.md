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
GROQ_API_KEY=your_groq_key
EMBEDDING_MODEL=intfloat/multilingual-e5-large
EMBEDDING_MODEL_FALLBACK=sentence-transformers/all-MiniLM-L6-v2
USE_SUPABASE=true
```

If you are running locally on Windows, use the project virtual environment before running any commands.

## Run it locally

Install dependencies:

```bash
pip install -r requirements.txt
```

Run ingestion:

```bash
python ingestor.py
```

Start the backend:

```bash
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8010
```

Open the app in your browser at:

```text
http://127.0.0.1:8010
```

## Supabase migration

The repository uses Supabase as the vector store. Before running ingestion, make sure the Supabase SQL migration has been applied so `legal_documents.embedding` is `vector(1024)` and the `search_legal_documents` RPC exists.

## Project layout

- `backend/` - FastAPI app and API routes
- `frontend/` - HTML, CSS, and JavaScript for the UI
- `ingestor.py` - PDF and source ingestion script
- `supabase-schema.sql` - main schema/migration file
- `QUICKSTART.md` - setup notes and migration guide

## Useful endpoints

- `GET /` - UI
- `GET /api/health` - health and readiness
- `GET /api/domains` - supported domain list
- `GET /api/sources` - configured dynamic sources
- `POST /api/query` - ask a legal question
- `POST /api/upload-pdf` - upload a new PDF

## Notes

- The embedding model can take a while to load the first time.
- If the model is unavailable, the app falls back to a smaller option.
- Uploaded and ingested content is stored in Supabase, so it survives app restarts.

## If something looks off

- Check `.env` for `SUPABASE_URL`, `SUPABASE_API_KEY`, and `GROQ_API_KEY`.
- Re-run the Supabase migration if the vector search RPC or embedding column is missing.
- If ingestion fails, run it once in the terminal and read the exact error before changing anything else.
