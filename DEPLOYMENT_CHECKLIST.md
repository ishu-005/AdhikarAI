# Pre-Deployment Checklist

## Backend (Render) - Free Tier Ready ✓
- [x] `render.yaml` configured with free tier settings
- [x] `runtime.txt` specifies Python 3.11
- [x] `requirements.txt` optimized (lightweight fallback options available)
- [x] `Procfile` as backup start command
- [x] `.env.example` with all required variables documented
- [x] Health check endpoint configured (`/api/health`)
- [x] CORS enabled for all origins (configurable via env)
- [x] Persistent disk (1GB) at `/opt/render/chroma_store`

## Frontend (Vercel) - Free Tier Ready ✓
- [x] Static site (no serverless functions needed)
- [x] `vercel.json` configured with rewrites
- [x] `.vercelignore` excludes unnecessary files
- [x] Relative API paths in `app.js` (works with any backend)
- [x] Static file caching headers configured
- [x] SPA route handling (all routes → index.html)

## Deployment Steps

### 1. Deploy Backend First
```bash
# In Render dashboard:
- Click "New +" → "Web Service"
- Connect your GitHub repo
- Select Python runtime
- Name: adhikarai-backend
- Plan: Free
- Set GROQ_API_KEY environment variable
- Deploy
# Note your Render URL: https://adhikarai-backend.onrender.com
```

### 2. Update Frontend Configuration
```bash
# After Render backend is live:
# Update root vercel.json line 5 with your Render URL
```

### 3. Deploy Frontend
```bash
# In Vercel dashboard:
- Click "New Project"
- Select your GitHub repo
- Framework: Other (static)
- Import project
# It will auto-deploy from root vercel.json
```

## Environment Variables to Set

### Render Backend (Required)
```
GROQ_API_KEY=sk-...  # Get from https://console.groq.com
```

### Render Backend (Recommended)
```
ALLOWED_ORIGINS=https://your-vercel-domain.vercel.app
LOG_LEVEL=INFO
EMBEDDING_MODEL_FALLBACK=hashing-384-v1
RERANKER_ENABLED=false
```

### Render Backend (Optional - for chat persistence)
```
USE_SUPABASE=true
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_API_KEY=eyJ...
```

## Free Tier Limits

### Render (Backend)
- Memory: 512MB
- Disk: 1GB (Chroma vector store)
- Connections: Limited
- Build timeout: 15 minutes
- Auto-sleeps after 15 minutes of inactivity
- **Cost**: $0/month on free tier

### Vercel (Frontend)
- Build minutes: 150/month
- Serverless functions: N/A (static site)
- Static assets: Unlimited
- Bandwidth: Generous, no overages
- **Cost**: $0/month on free tier

## Optimization Applied

### Memory Savings
- Fallback to lightweight hashing model: 384-dim (~100MB)
- Reranker disabled by default (saves 300MB+)
- Low-memory embedding model configuration

### Cold Start Handling
- Accept 30-90 second boot time on Render free tier
- Health check configured every 30s to detect readiness
- Chroma data persists across restarts

### Vercel Static Serving
- No cold starts (static files instantly available)
- Caching headers configured for assets
- Automatic compression enabled

## Testing

After deployment, verify:

```bash
# 1. Check Render health
curl https://YOUR_RENDER_URL/api/health

# 2. Visit Vercel frontend
https://YOUR_VERCEL_URL

# 3. Try a legal query (test end-to-end)
# Should see "model_loaded": true in console/network tab
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "503 Service Unavailable" | Render cold start - wait 1-2 min |
| "GROQ API key invalid" | Check GROQ_API_KEY in Render env vars |
| "CORS error" | Update ALLOWED_ORIGINS in Render env |
| "Out of memory" | Rendering.yaml already uses fallbacks |
| "Chroma not found" | Disk auto-created, ignore warning on first boot |

## Cost Summary

| Service | Free Tier | When to Upgrade |
|---------|-----------|-----------------|
| **Render** | 750 hrs/month | When consistently running >31 days |
| **Vercel** | $0 (static) | Only if adding dynamic features |
| **Groq API** | Pay-per-use | When query volume >1000/month (~$1-5) |
| **Supabase** (optional) | 500MB, 3 connections | When needing backup/scaling |

**Expected free tier cost: $0-5/month** (mainly Groq API usage)

---

## Next Steps After Deployment

1. ✓ Deploy and test basic functionality
2. Monitor cold start times and optimization needs
3. Consider Supabase if persistent chat history needed
4. Upgrade Render plan ($7+/month) when ready to scale
5. Add custom domain to both services (free)
