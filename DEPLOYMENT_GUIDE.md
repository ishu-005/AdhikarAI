# AdhikarAI Deployment Guide

## Quick Summary

This guide walks through deploying AdhikarAI on free tier services:
- **Frontend**: Vercel (static files)
- **Backend API**: Render 
- **Database & Storage**: Supabase (PostgreSQL + pgvector + file storage)

Total cost: **$0/month** (with free tier limitations)

---

## Phase 1: Supabase Setup (Persistent Storage)

### 1. Create Supabase Account
1. Go to https://supabase.com
2. Click **Sign Up** → Create account
3. Create new organization
4. Create new project:
   - **Name**: adhikarai
   - **Database Password**: Save this securely
   - **Region**: Choose closest to your users
5. Wait for project initialization (2-3 minutes)

### 2. Get Supabase Credentials
Once project loads, navigate to **Project Settings** (gear icon):
- **Project URL** → Copy to `SUPABASE_URL` in `.env`
  - Format: `https://[project-id].supabase.co`
- **Project API Keys** → Copy **Service Role** key to `SUPABASE_API_KEY`
  - WARNING: This is SECRET – never commit to GitHub
  - The **Anon Key** is public; use that in frontend if needed
- Note the **Database Password** you created

### 3. Create Database Tables
In Supabase dashboard:
1. Click **SQL Editor** → **New Query**
2. Copy entire contents of `supabase-schema.sql` from your repo
3. Paste into the SQL editor
4. Click **Run** → Wait for success message
5. Tables created:
   - `chats` – Stores conversation threads
   - `chat_metadata` – Stores chat names
   - `documents` – Stores embeddings (for future use)

### 4. Create Storage Bucket
1. Click **Storage** in left menu
2. Click **New Bucket** → Name: `pdfs`
3. Set to **Public** (so PDFs are downloadable)
4. Create folders matching your domain structure:
   - `pdfs/criminal_law/`
   - `pdfs/labour/`
   - `pdfs/human_rights/`
   - `pdfs/citizen_rights/`
   - `pdfs/consumer/`
   - etc.

✅ **Supabase setup complete**

---

## Phase 2: Backend Deployment (Render)

### 1. Push Code to GitHub
```bash
cd d:\AdhikarAI

# Initialize git (if not already done)
git init

# Create .gitignore
echo ".env" >> .gitignore
echo ".venv" >> .gitignore
echo "chroma_store/" >> .gitignore
echo "__pycache__/" >> .gitignore
echo "pdfs/" >> .gitignore

# Commit code
git add .
git commit -m "Ready for deployment"

# Add remote and push (replace with your GitHub repo)
git remote add origin https://github.com/YOUR_USERNAME/adhikarai.git
git branch -M main
git push -u origin main
```

### 2. Deploy on Render
1. Go to https://render.com
2. Sign up with GitHub account
3. Click **New** → **Web Service**
4. Select your GitHub repo (`adhikarai`)
5. Configure:
   - **Name**: `adhikarai-backend`
   - **Runtime**: Python 3.11
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app:app --host 0.0.0.0 --port $PORT`
6. Click **Advanced** and add **Environment Variables**:
   ```
   GROQ_API_KEY = [your Groq API key]
   SUPABASE_URL = [from Supabase settings]
   SUPABASE_API_KEY = [Service Role key from Supabase]
   SUPABASE_BUCKET_NAME = pdfs
   USE_SUPABASE = true
   ALLOWED_ORIGINS = *
   LOG_LEVEL = INFO
   ```
7. Select **Free Plan**
8. Click **Create Web Service** → Wait 3-5 minutes for deployment

### 3. Get Backend URL
Once deployed:
- Render shows your service URL: `https://adhikarai-backend.onrender.com`
- Free tier auto-sleeps after 15 min inactivity (first request takes 30s to wake)
- Test health endpoint: `https://adhikarai-backend.onrender.com/api/health`
  - Should return: `{"status": "ok", ...}`

✅ **Backend deployed**

---

## Phase 3: Frontend Deployment (Vercel)

### 1. Prepare Frontend Files
Files needed for Vercel:
```
templates/index.html
static/app.js
static/styles.css
vercel.json
```

These are already in your repo.

### 2. Deploy on Vercel
1. Go to https://vercel.com
2. Sign up with GitHub
3. Click **Add New** → **Project**
4. Import your GitHub repo
5. Configure:
   - **Build Command**: `echo 'Static build'` (we're deploying static files)
   - **Output Directory**: `./`
6. Add **Environment Variables**:
   ```
   NEXT_PUBLIC_API_URL = https://adhikarai-backend.onrender.com
   ```
7. Click **Deploy** → Wait 1-2 minutes

### 3. Get Frontend URL
Once deployed:
- Vercel shows your app URL: `https://adhikarai.vercel.app` (or custom domain)
- Test by opening the URL in browser

### 4. Update Render ALLOWED_ORIGINS
1. Go back to Render dashboard
2. Select `adhikarai-backend` service
3. Click **Environment**
4. Edit `ALLOWED_ORIGINS`:
   ```
   https://adhikarai.vercel.app,http://localhost:3000,https://adhikarai-backend.onrender.com
   ```
5. Click **Save** (auto-redeploys)

✅ **Frontend deployed**

---

## Phase 4: Verification

### Test from Vercel Frontend
Open `https://adhikarai.vercel.app` and test:

- [ ] **New Chat**: Click "New Chat" → Should create thread
- [ ] **Send Message**: Type question → Get response from backend
- [ ] **Upload PDF**: Upload a PDF from one of the domains
- [ ] **Toggle Insights**: Show/hide insights panel
- [ ] **Dark/Light Theme**: Toggle theme → Should persist
- [ ] **Delete Chat**: Delete a conversation
- [ ] **Data Persistence**: Refresh page → Chats still visible (Supabase)

### Check Browser Console (F12)
- Should show **zero CORS errors**
- API calls should show `/api/...` paths

### Test Backend Health
```bash
curl https://adhikarai-backend.onrender.com/api/health
```

Should return:
```json
{
  "status": "ok",
  "time": "2026-04-27T...",
  "model_loaded": true,
  "vector_store_ready": true
}
```

---

## Phase 5: Local Development (Keep Working Locally)

You can still run locally while deployed in cloud:

```bash
# Set USE_SUPABASE=false to use local Chroma
$env:USE_SUPABASE="false"

# Or update .env
USE_SUPABASE=false

# Run locally
python app.py
```

Then open: `http://localhost:8000`

**All features work locally** – chats stored in local memory, PDFs in `pdfs/` folder.

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| **CORS error on Vercel** | Check `ALLOWED_ORIGINS` on Render includes Vercel domain |
| **Backend URL not found** | Render free tier might be sleeping; first request takes 30s |
| **Chats not persisting** | Verify `USE_SUPABASE=true` and Supabase credentials are correct |
| **Upload fails** | Check Supabase Storage bucket exists and is public |
| **Local mode broken** | Set `USE_SUPABASE=false` in `.env` |
| **pdfs/ folder empty after deploy** | Render free tier doesn't persist disk; upload PDFs via UI to Supabase |

---

## Key Environment Variables

### Local Development (.env)
```env
USE_SUPABASE=false
CHROMA_PATH=./chroma_store
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000
```

### Render Production (.env.production)
```env
USE_SUPABASE=true
SUPABASE_URL=https://[project-id].supabase.co
SUPABASE_API_KEY=[service_role_key]
SUPABASE_BUCKET_NAME=pdfs
ALLOWED_ORIGINS=https://your-vercel-url.vercel.app
```

---

## Next Steps

1. **After deployment**: Monitor Render/Vercel logs for errors
2. **Upload legal documents** to Supabase Storage bucket via the web UI
3. **Test with real queries** from Vercel frontend
4. **Set up custom domain** (optional, in Vercel settings)
5. **Configure email notifications** (optional, in Render settings)

---

## Cost Summary (Free Tier)

| Service | Cost | Limit |
|---------|------|-------|
| **Supabase** | $0 | 1 database, 500MB storage, 2GB bandwidth |
| **Render** | $0 | 750 hours/month, auto-sleeps after 15 min |
| **Vercel** | $0 | Unlimited requests, 100GB/month bandwidth |
| **Total** | **$0** | Sufficient for MVP |

---

## Advanced: Scale Beyond Free Tier

When you outgrow free tiers:
- **Render**: Upgrade to Starter ($7/month) for always-on
- **Supabase**: Upgrade to $25/month Pro for more storage
- **Vercel**: Stays free even with high traffic

---

## Support

For issues, check:
- Render logs: Dashboard → Service → Logs
- Vercel logs: Dashboard → Deployments → Logs
- Supabase logs: Dashboard → Database → Logs
