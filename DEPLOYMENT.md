# AdhikarAI Deployment (Hugging Face Spaces)

This app can be deployed on Hugging Face as a Docker Space. It serves UI (`/`), static files (`/static/*`), and API (`/api/*`) from one FastAPI process.

## Deployment Target

- Space type: `Docker`
- Runtime port: `7860`
- Start command: `uvicorn backend.app:app --host 0.0.0.0 --port 7860`

## Files Used for Hugging Face

- `Dockerfile` at repo root
- `.dockerignore` at repo root

## Hugging Face Console Steps

1. Open Hugging Face and create a new Space.
2. Select `Docker` as the SDK.
3. Choose your Space visibility.
4. Connect GitHub repo or push this repo to the Space.
5. In Space Settings -> Variables and secrets, add required env vars.
6. Let the Space build and start.
7. Open the Space URL and test `/api/health`.

## Quickstart Commands (From Local Machine)

Use these commands to push your current app to the Space repository.

1. Clone the Space repository:

	git clone https://huggingface.co/spaces/ishu005/AdhikarAI

2. Install HF CLI on Windows PowerShell (if needed):

	powershell -ExecutionPolicy ByPass -c "irm https://hf.co/cli/install.ps1 | iex"

3. Optional: download current Space snapshot:

	hf download ishu005/AdhikarAI --repo-type=space

4. Copy this project files into the cloned Space folder.

5. Commit and push:

	git add .
	git commit -m "Deploy AdhikarAI Docker Space"
	git push

When prompted for password, use a Hugging Face access token with write permission.

## Required Environment Variables

At minimum:

```env
GROQ_API_KEY=sk-...
```

Recommended:

```env
PORT=7860
LOG_LEVEL=INFO
ALLOWED_ORIGINS=*
RERANKER_ENABLED=false
EMBEDDING_MODEL_FALLBACK=hashing-384-v1
```

Optional (Supabase):

```env
USE_SUPABASE=true
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_API_KEY=eyJ...
SUPABASE_BUCKET_NAME=pdfs
```

## Verify Deployment

After build succeeds, open:

```text
https://huggingface.co/spaces/<username>/<space-name>
```

Health endpoint:

```text
https://<space-subdomain>.hf.space/api/health
```

## Notes

- Hugging Face Spaces storage is ephemeral unless persistent storage is enabled.
- If you need stable long-term vector data, use Supabase/pgvector or Space persistent storage.
