# Deploying AdhikarAI for Free

Final recommended architecture:

| Piece | Free service | Why |
|---|---|---|
| Frontend | Vercel | Native Next.js hosting, CDN, simple `NEXT_PUBLIC_API_BASE` config |
| Backend | Hugging Face Spaces | Free Docker CPU Space with enough RAM for this Python API |
| Database / vector store | Supabase | Postgres + pgvector for document chunks, chat history, and search RPCs |
| LLM | Groq | Fast hosted generation |
| Embeddings / reranker | Cohere | Cloud embeddings and reranking, no local ML model memory cost |

Do not deploy the backend on Render free for the main demo. Render free web services spin down after 15 minutes idle and take about a minute to wake up. Hugging Face Spaces free CPU hardware is a better fit for this backend.

---

## 1. Supabase

1. Create a Supabase project.
2. Open SQL Editor.
3. Paste and run `supabase_migration.sql`.
4. Confirm the verification rows at the bottom are `true`.
5. Copy:
   - `SUPABASE_URL`
   - `SUPABASE_API_KEY` as the `service_role` key

Run the migration again whenever `supabase_migration.sql` changes.

---

## 2. Ingest Data

Run ingestion locally after setting `.env`:

```powershell
.venv\Scripts\python.exe ingestor.py
```

The backend uses cloud embeddings, so the database stores vectors in Supabase. If you change `EMBEDDING_PROVIDER`, wipe `legal_documents` and re-ingest.

---

## 3. Backend on Hugging Face Spaces

1. Create a new Hugging Face Space.
2. Select **Docker** as the SDK.
3. Connect this GitHub repo or push the repo to the Space.
4. Keep the README frontmatter:

```yaml
sdk: docker
app_port: 7860
```

5. Add Space secrets:

```env
SUPABASE_URL=...
SUPABASE_API_KEY=...
GROQ_API_KEY=...
COHERE_API_KEY=...
EMBEDDING_PROVIDER=cohere
USE_SUPABASE=true
ALLOWED_ORIGINS=https://your-vercel-app.vercel.app
ALLOWED_ORIGIN_REGEX=https://.*\.vercel\.app
```

6. Deploy.
7. Verify:

```text
https://your-space.hf.space/api/health
```

Expected:

```json
{
  "status": "ok",
  "vector_store_ready": true
}
```

---

## 4. Frontend on Vercel

1. Import the same GitHub repo in Vercel.
2. Set **Root Directory** to `frontend-next`.
3. Add:

```env
NEXT_PUBLIC_API_BASE=https://your-space.hf.space
```

4. Deploy.
5. Open the Vercel URL and test a question.

---

## 5. CORS Wiring

After Vercel deploys, copy the production Vercel URL into the Hugging Face Space secret:

```env
ALLOWED_ORIGINS=https://your-vercel-app.vercel.app
```

Preview deployments are covered by:

```env
ALLOWED_ORIGIN_REGEX=https://.*\.vercel\.app
```

---

## Local Development

Backend:

```powershell
py run.py
```

Frontend:

```powershell
cd frontend-next
npm install
npm run dev
```

Local frontend env:

```env
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

---

## Free-Tier Notes

- Hugging Face Docker Spaces support custom FastAPI containers and expose `app_port: 7860`.
- Hugging Face free CPU Spaces provide 2 vCPU, 16 GB RAM, and 50 GB non-persistent disk by default.
- Store long-term data in Supabase, not the backend filesystem.
- Render free web services are acceptable for small demos, but cold starts and outbound traffic limits make them less suitable here.
