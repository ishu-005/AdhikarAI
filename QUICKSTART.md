## 🚀 AdhikarAI Supabase Migration - Quick Start Guide

### Prerequisites
- Supabase project created (https://supabase.com)
- Python 3.8+
- Environment variables configured in `.env`

### Step 1: Apply Database Migration (5 minutes)

```bash
# 1. Login to Supabase Dashboard
# 2. Go to SQL Editor → New Query
# 3. Copy-paste entire contents of supabase_migration.sql
# 4. Click "Run"
# 5. Verify setup completed at bottom (check marks should appear)
```

**Verify installation:**
```sql
-- Run this in Supabase SQL Editor to confirm
SELECT 'pgvector' as check_item, EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector') as result
UNION ALL
SELECT 'legal_documents', EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = 'legal_documents')
UNION ALL
SELECT 'search function', EXISTS(SELECT 1 FROM pg_proc WHERE proname = 'search_legal_documents');
```

### Step 2: Update Environment Variables

Create or update `.env` file:

```env
# Supabase (required)
SUPABASE_URL=https://[your-project-id].supabase.co
SUPABASE_API_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Optional: Customize embedding model
EMBEDDING_MODEL=intfloat/multilingual-e5-large
EMBEDDING_MODEL_FALLBACK=sentence-transformers/all-MiniLM-L6-v2

# Groq API (for LLM)
GROQ_API_KEY=gsk_...

# Optional: PDF storage path
CHROMA_PATH=./chroma_store
```

**Where to find Supabase credentials:**
1. Supabase Dashboard → Settings → API
2. Copy `URL` → `SUPABASE_URL`
3. Copy `anon public` key → `SUPABASE_API_KEY`

### Step 3: Install/Update Dependencies

```bash
# Activate your virtual environment first
pip install -r requirements.txt

# If upgrading from ChromaDB:
pip uninstall chromadb -y
pip install psycopg2-binary
```

### Step 4: Ingest PDFs (Optional - Re-index Existing Documents)

```bash
# First time setup or re-indexing
python ingestor.py

# This will:
# - Read PDFs from pdfs/ directory
# - Generate embeddings using sentence-transformers
# - Insert into Supabase legal_documents table
# - Estimate: ~1-2 seconds per PDF
```

### Step 5: Start the Application

```bash
# Terminal 1: Start backend
python -m uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Open browser
# Visit: http://localhost:8000
```

### Step 6: Test the Setup

**Test 1: Health Check**
```bash
curl http://localhost:8000/api/health
# Expected: {"status":"ok"}
```

**Test 2: Query with Cache**
```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What are the rights of citizens?",
    "language": "en",
    "conversation_id": "test"
  }'

# Should return within 1-2 seconds on first call
# Cached responses appear within 100ms
```

**Test 3: Check Supabase Data**
```sql
-- Run in Supabase SQL Editor
SELECT COUNT(*) as total_documents FROM legal_documents;
SELECT domain, COUNT(*) FROM legal_documents GROUP BY domain;
```

### Troubleshooting

#### Error: "Supabase client not configured"
- Check `SUPABASE_URL` and `SUPABASE_API_KEY` in `.env`
- Verify they match exactly from Supabase dashboard
- Restart the application

#### Error: "relation 'legal_documents' does not exist"
- Run `supabase_migration.sql` again in SQL Editor
- Verify all statements completed successfully

#### Error: `column "url" does not exist`
- Make sure you pasted the latest `supabase_migration.sql` from this repo, not an older tab or cached copy
- Run the migration again after clearing the SQL editor contents completely
- If the table already exists, run this repair block once before the rest of the migration:

```sql
ALTER TABLE legal_documents ADD COLUMN IF NOT EXISTS url TEXT;
DROP INDEX IF EXISTS legal_docs_url_idx;
CREATE INDEX IF NOT EXISTS legal_docs_url_idx ON legal_documents(url);
```

If you are starting from a clean database, you do not need the repair block; just run the updated migration file.

#### Error: policy "Allow public read" for table "legal_documents" already exists
- Use the updated `supabase_migration.sql` from this repo; it now drops existing policies and triggers before recreating them
- Clear the SQL editor and rerun the full script from the top
- If you still have an older tab open, close it so Supabase does not rerun stale SQL

#### Slow vector search
- Run `REINDEX TABLE legal_documents USING ivfflat;` in Supabase
- Consider increasing IVFFlat list size for larger datasets
- Check Supabase database resource usage

#### Cache not working
- Verify `OptimizationCache` is initialized in `backend/app.py`
- Check response includes `"_cached": true` field
- Default TTL is 30 minutes

### Performance Expectations

| Operation | Time | Notes |
|-----------|------|-------|
| Vector search | 100-300ms | Depends on dataset size |
| LLM generation | 1-3s | Varies by Groq API load |
| Cached response | <100ms | Same query within 30min |
| PDF ingestion | 1-2s per PDF | Parallel processing enabled |

### Monitoring & Maintenance

```bash
# Check ingestion progress
tail -f logs/ingestor.log

# Monitor Supabase usage
# Dashboard → Database → Logs

# Clear cache (optional restart)
# Backend automatically manages with TTL

# Backup data
pg_dump postgresql://[user]:[pass]@db.supabase.co:5432/postgres > backup.sql
```

### Migration Rollback (If Needed)

To revert to ChromaDB (not recommended):
```bash
# 1. Reinstall ChromaDB
pip install chromadb

# 2. Comment out Supabase code in backend/app.py
# 3. Run application with CHROMA_PATH set

# Note: You'll lose optimizations and caching benefits
```

### Next: Re-ingest Existing PDFs

If you already have the PDFs in the `pdfs/` folder, just run:

```bash
python ingestor.py
```

That will regenerate embeddings and push them directly into Supabase `legal_documents`.

If you need to migrate legacy ChromaDB data, export it into a simple JSON or CSV format first, then feed the records through the same Supabase insert flow used in `ingestor.py`.

### Support

- Check `SUPABASE_MIGRATION.md` for technical details
- Review `backend/app.py` for implementation examples
- See `frontend/static/app.js` for UI integration

---

**You're all set! 🎉 AdhikarAI is now running on Supabase pgvector with optimized performance and improved UI.**

