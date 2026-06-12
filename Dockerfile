# ─────────────────────────────────────────────────────────────
# Stage 1: build the Next.js UI into a static export.
# next.config.js writes the export to ../frontend/static-next
# ─────────────────────────────────────────────────────────────
FROM node:20-slim AS ui
WORKDIR /build
COPY frontend-next/package.json frontend-next/package-lock.json* frontend-next/
RUN cd frontend-next && npm install
COPY frontend-next/ frontend-next/
# STATIC_EXPORT=true makes Next emit ./out for FastAPI to serve (single container).
RUN cd frontend-next && STATIC_EXPORT=true npm run build

# ─────────────────────────────────────────────────────────────
# Stage 2: Python backend that also serves the static UI.
# ─────────────────────────────────────────────────────────────
FROM python:3.11-slim

# Embeddings + reranking run via cloud APIs (Cohere/Jina) — no local ML models,
# so the image stays small and fits free-tier 512MB RAM hosts.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r /app/requirements.txt

COPY . /app
# Bring in the compiled UI (Next static export at frontend-next/out), served at "/".
COPY --from=ui /build/frontend-next/out /app/frontend-next/out

EXPOSE 7860

CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "7860"]
