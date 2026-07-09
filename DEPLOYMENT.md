# Deploying cascAIde

cascAIde ships as **one container**: a FastAPI backend that also serves the built React
frontend. Everything else is a hosted service you point it at with env vars.

## What runs where

| Piece | Where it lives | You do |
|---|---|---|
| **Backend + Frontend** | one container (this repo's `Dockerfile`) | deploy to Render / Railway / Fly |
| **Butterbase** | hosted (`api.butterbase.ai`), already provisioned | set keys + add your prod URL to CORS & OAuth |
| **Neo4j** | Neo4j Aura (free) or self-hosted | create an instance, copy URI + password |
| **Cognee Cloud** | hosted (your tenant) | copy base URL + API key |
| **Groq / OpenRouter** | hosted APIs | copy API keys |
| **Daytona** | hosted (optional) | leave `DEPCOVER_USE_DAYTONA=false` to skip |

The frontend calls the backend **same-origin** and derives the GitHub OAuth redirect from
`window.location.origin`, so there is **no separate frontend deploy and no hardcoded URL** —
one service, one domain.

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

## 3. Point Butterbase at your prod URL
Once you have the deployed URL (e.g. `https://cascaide-xxxx.onrender.com`), it must be
allow-listed or GitHub sign-in and API calls will be blocked by CORS/OAuth. Two updates:

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
- **Daytona** is off by default; the transplant still validates via the non-sandbox path. Flip
  `DEPCOVER_USE_DAYTONA=true` + set `DAYTONA_API_KEY` to enable the real `node --check` sandbox.
