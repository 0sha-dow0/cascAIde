# Deploying cascAIde

Two hosting shapes are supported. Pick one:

- **Split (sponsor setup):** React **UI on Butterbase** (`*.butterbase.dev`) + Python **backend
  on Render**. Best sponsor coverage — Butterbase hosts the UI *and* powers auth/GitHub.
- **All-in-one:** one container (backend serves the built UI) on Render. Simplest, one URL.

Either way, everything else is a hosted service you point it at with env vars.

## What runs where

| Piece | Where it lives | You do |
|---|---|---|
| **Frontend (React)** | Butterbase `*.butterbase.dev` (split) or inside the container (all-in-one) | build with `VITE_API_BASE` → deploy |
| **Backend (Python)** | Render / Railway / Fly (`Dockerfile`) — Butterbase can't run Python | deploy container + set env vars |
| **Butterbase** | hosted (`api.butterbase.ai`), already provisioned | keys + add your UI origin to CORS & OAuth |
| **Neo4j** | Neo4j Aura (free) | copy URI + password |
| **Cognee Cloud** | hosted (your tenant) | copy base URL + API key |
| **Groq / OpenRouter** | hosted APIs | copy API keys |
| **Daytona** | hosted (optional) | leave `DEPCOVER_USE_DAYTONA=false` to skip |

The GitHub OAuth redirect is derived from `window.location.origin`, so there's no hardcoded
URL — only two knobs make the split work: **`VITE_API_BASE`** (UI build → backend origin) and
**`DEPCOVER_CORS_ORIGINS`** (backend env → the UI origin, so the browser may call it).

## 1. Gather credentials
Copy `.env.example` and fill it (you already have these in your local `backend/.env`):
- `GROQ_API_KEY`, `OPENROUTER_API_KEY`
- `DEPCOVER_NEO4J_URI` + `NEO4J_PASSWORD` (from Neo4j Aura → "Create instance", free tier)
- `DEPCOVER_BUTTERBASE_BASE_URL=https://api.butterbase.ai`, `DEPCOVER_BUTTERBASE_APP_ID`, `BUTTERBASE_KEY` (service key)
- `DEPCOVER_COGNEE_BASE_URL` + `COGNEE_API_KEY`
- LLM role vars (defaults in `.env.example` work as-is on Groq)

## 2. Deploy the container

### Render (recommended — free, deploys from GitHub)
1. Render → **New → Web Service** → connect the `cascAIde` repo.
2. Runtime **Docker** (it auto-detects the `Dockerfile`). Render injects `$PORT`.
3. **Environment → Add from .env**: paste every line of your filled env file.
4. Create. First build ~3–5 min. You get `https://cascaide-xxxx.onrender.com`.

### Railway / Fly.io (alternatives)
- **Railway**: New Project → Deploy from repo → it builds the `Dockerfile`; add the same env vars.
- **Fly.io**: `fly launch` (detects the Dockerfile) → `fly secrets set KEY=value ...` → `fly deploy`.

## 2b. (Split) Deploy the UI to Butterbase
Once the backend has a URL (e.g. `https://cascaide-xxxx.onrender.com`):
1. Build the UI pointing at it: `cd frontend && VITE_API_BASE=https://cascaide-xxxx.onrender.com npm run build`.
2. Zip the output: `cd dist && zip -r ../frontend.zip .` (use forward slashes — Git Bash/WSL on Windows).
3. `create_frontend_deployment(app_id, framework="react-vite")` → PUT the zip to the returned URL → `manage_frontend(start_deployment)`. Result: `https://<app>.butterbase.dev`.
4. Set the backend's `DEPCOVER_CORS_ORIGINS=https://<app>.butterbase.dev` and redeploy the backend.

(I can drive steps 3–4 for you via the Butterbase MCP once you paste the backend URL.)

## 3. Point Butterbase at your UI origin
Your UI origin (the `butterbase.dev` URL, or the Render URL for all-in-one) must be
allow-listed or GitHub sign-in is blocked by CORS/OAuth. Two updates:

1. **CORS** — add the prod origin to the Butterbase app's allowed origins.
2. **GitHub OAuth redirect** — add `https://<your-prod-url>/#console` to the app's allowed
   `redirect_to` targets (the GitHub OAuth App *callback* stays `…/auth/<app_id>/oauth/github/callback`
   on Butterbase's domain and does **not** change).

I can make both changes for you via the Butterbase MCP as soon as you paste the deployed URL.

## 4. Verify
1. Open the URL → landing page → **Launch**.
2. **Sign in with GitHub** → **Connect GitHub** (in the account menu).
3. Scan a repo you own → **Fire CVE** → **Run transplant** → **Accept** → a real PR opens.
4. `GET /health` returns `{"ok": true, "use_fakes": false}`.

## Notes
- **Free-tier sleep**: Render/Neo4j-Aura free tiers idle out; the first request after idle is slow.
- **Secrets**: only ever set them as host env vars. `backend/.env` and real secrets are git-ignored.
- **Daytona is required and stays ON** (`DEPCOVER_USE_DAYTONA=true` + `DAYTONA_API_KEY`): every
  transplant is compiled with `node --check` in a real, network-blocked `node:20-alpine` sandbox,
  so a rewrite only ships if it actually builds. The image (`node:20-alpine`) is created fresh per
  run and deleted after. Requires the container to include the `daytona` pip package (it does).
