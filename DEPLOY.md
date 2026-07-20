# Free Deployment Guide

Three pieces, three free hosts. The database (Supabase) is already hosted —
you only deploy the **backend** and **frontend**.

| Piece | Host | Free tier caveat |
|-------|------|------------------|
| Database | Supabase (existing) | — nothing to change |
| Backend (FastAPI) | Render | Sleeps after 15 min idle → ~30–50s cold start |
| Frontend (Vite build) | Cloudflare Pages / Vercel | None — static CDN |

Deploy the backend first so you have its URL for the frontend.

## 1. Backend → Render

1. Push this repo to GitHub.
2. Render → **New → Blueprint**, select the repo. It reads `render.yaml`.
3. In the service's **Environment** tab, fill the secrets:
   `SUPABASE_URL`, `SUPABASE_KEY`, `API_FOOTBALL_KEY` (same values as your `.env`).
4. Deploy. Note the URL, e.g. `https://transfer-idss-api.onrender.com`.
5. Verify: open `<url>/health`.

## 2. Frontend → Cloudflare Pages (or Vercel)

Settings:
- **Build command:** `npm run build`
- **Output directory:** `dist`
- **Root directory:** `frontend`
- **Environment variable:** `VITE_API_URL = https://transfer-idss-api.onrender.com`
  (must be set at build time — Vite inlines it into the bundle).

Deploy, then note the URL, e.g. `https://transfer-idss.pages.dev`.

## 3. Close the CORS loop

Back in Render, set `ALLOWED_ORIGINS` to the frontend URL from step 2
(comma-separate multiple, no trailing slash):

```
ALLOWED_ORIGINS=https://transfer-idss.pages.dev
```

Render redeploys automatically. The app is now live.

## Demo tip

The free backend sleeps when idle. ~1 minute before a demo, open
`<backend-url>/health` once to warm it so the first real request isn't slow.

## Local dev is unchanged

Both defaults fall back to localhost, so `uvicorn` + `npm run dev` still work
with no env vars set.
