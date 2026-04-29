# AdhikarAI - Free Tier Deployment Guide

## Vercel Frontend Deployment (Free Tier)

### Prerequisites
1. GitHub account with this repository
2. Vercel account (free)

### Steps
1. Go to [vercel.com](https://vercel.com)
2. Click "New Project" → Select your GitHub repository
3. **Configure Settings:**
   - Framework: Other (it's a static site)
   - Build Command: `echo 'Static build complete'`
   - Output Directory: `frontend`
   - Install Command: (leave empty)

4. **Set Environment Variables:**
   - `NEXT_PUBLIC_API_URL`: `https://your-backend-url.onrender.com` (get this after Render deployment)

5. Click "Deploy"
6. Once deployed, note your Vercel URL (e.g., `https://adhikarai.vercel.app`)

---

## Render Backend Deployment (Free Tier)

### Prerequisites
1. GitHub account with this repository
2. Render account (free)

### Steps
1. Go to [render.com](https://render.com)
2. Click "New +" → Select "Web Service"
3. **Connect Repository:**
   - Select GitHub repository
   - Choose deployment branch (main/master)

4. **Configure Deployment:**
   - Service Name: `adhikarai-backend` (or your choice)
   - Environment: `Python 3.11`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn app:app --host 0.0.0.0 --port $PORT`
   - Plan: **Free** (important!)

5. **Set Environment Variables** (Required):
   ```
   PORT=8000
   GROQ_API_KEY=sk-... (get from https://console.groq.com)
   ALLOWED_ORIGINS=https://your-frontend-url.vercel.app,http://localhost:3000
   ```

   **Optional (for chat persistence):**
   ```
   USE_SUPABASE=false  (set to "true" to enable Supabase)
   SUPABASE_URL=https://xxxxx.supabase.co
   SUPABASE_API_KEY=eyJ...
   ```

6. **Disk Storage (for vector database):**
   - Render automatically provisions 1GB at `/opt/render/chroma_store`

7. Click "Create Web Service"
8. Wait for deployment (2-3 minutes)
9. Once deployed, you'll get a URL like `https://adhikarai-backend.onrender.com`

---

## Update Frontend API URL

After Render deployment, update your Vercel environment:

1. Go to Vercel dashboard → Your project
2. Settings → Environment Variables
3. Update `NEXT_PUBLIC_API_URL` with your Render backend URL
4. Redeployment will trigger automatically

---

## Free Tier Limitations & Workarounds

### Render Free Tier
| Feature | Limit | Workaround |
|---------|-------|-----------|
| **Cold Start** | ~1-2 min on idle | Accept delay on first request after 15min idle |
| **Memory** | 512MB | Set `EMBEDDING_MODEL_FALLBACK=hashing-384-v1` (fallback uses <100MB) |
| **Disk** | 1GB | Sufficient for chroma_store; use Supabase for chat history |
| **Build Time** | 15 min timeout | Keep requirements.txt minimal |
| **Restart Policy** | Daily restart | Automatic, app recovers from .chroma_store persistence |

### Vercel Free Tier
| Feature | Limit | Details |
|---------|-------|---------|
| **Serverless Functions** | 100GB/month | Static sites have no function limit |
| **Static Assets** | Unlimited | Perfect for frontend serving |
| **Bandwidth** | Generous | No overage charges on free tier |
| **Build Time** | 45 seconds | Our build is instant (static) |

---

## Optimization Tips for Free Tier Success

### 1. **Backend Memory Usage** (Critical for Render)
```env
EMBEDDING_MODEL_FALLBACK=hashing-384-v1          # <100MB (use for cold starts)
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2  # ~350MB
RERANKER_ENABLED=false                            # Saves 300MB+ on free tier
```

### 2. **Enable Supabase for Chat Persistence** (Recommended)
```env
USE_SUPABASE=true
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_API_KEY=your-service-role-key
```
- Free tier: 500MB storage, 3 connections
- Chroma data survives across Render restarts
- Chat history persisted

### 3. **Frontend Configuration**
- Static site on Vercel = no cold starts ✓
- API calls proxy through rewrites (vercel.json)
- Gzip compression enabled by default ✓

---

## Testing Deployment

### Test Backend Health
```bash
curl https://your-backend-url.onrender.com/api/health
```

Expected response:
```json
{
  "status": "ok",
  "time": "2024-04-28T10:30:00.000Z",
  "model_loaded": true,
  "vector_store_ready": true
}
```

### Test Frontend
1. Visit `https://your-frontend-url.vercel.app`
2. Try typing a legal question
3. Check browser console for API errors

---

## Monitoring & Troubleshooting

### Check Render Logs
1. Render Dashboard → Your service
2. "Logs" tab for real-time output
3. Look for:
   - "Initialization complete" = Ready ✓
   - "Groq generation failed" = Check API key ✗
   - "Out of memory" = Model too large for tier

### Check Vercel Logs
1. Vercel Dashboard → Your project
2. "Deployments" tab → Click active deployment
3. "Logs" for build and runtime errors

---

## Environment Variables Reference

**Backend Required (.env on Render):**
```
PORT=8000
GROQ_API_KEY=sk-...
```

**Backend Recommended:**
```
ALLOWED_ORIGINS=https://your-vercel-app.vercel.app
EMBEDDING_MODEL_FALLBACK=hashing-384-v1
RERANKER_ENABLED=false
```

**Backend Optional (Supabase):**
```
USE_SUPABASE=true
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_API_KEY=eyJ...
SUPABASE_BUCKET_NAME=pdfs
```

---

## Cost Estimate

| Service | Free Tier | Cost (if exceeding) |
|---------|-----------|-------------------|
| **Vercel** | Unlimited static sites | $0.15/GB bandwidth |
| **Render** | 750 compute hours/month | $0.10/hour after tier |
| **Supabase** (optional) | 500MB database | $0.115/GB over limit |
| **Groq API** | Pay-as-you-go | ~$0.0002-0.0008 per request |

**Monthly Cost on Free Tier: ~$0 (if within limits)**

---

## Support & Next Steps

1. **First Deploy:** Follow the step-by-step guide above
2. **Custom Domain:** Both Vercel and Render support custom domains (free)
3. **Database:** Migrate to Supabase for multi-instance scaling
4. **Scaling:** When free tier limits hit, upgrade Render to "$7/month" plan

For issues:
- Render: [Support](https://render.com/support)
- Vercel: [Support](https://vercel.com/support)
