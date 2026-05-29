# EconLens API v3.0

Business news analyser — economics, game theory & geopolitics.
**Keys live here. Visitors need none.**

---

## Endpoints

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/` | Health check + version |
| GET | `/health` | Key config status |
| GET | `/lenses` | All 6 economic lenses |
| GET | `/feed` | Today's analysed news feed (cached 30 min) |
| GET | `/feed?refresh=true` | Force fresh feed |
| POST | `/analyse` | Analyse a single story |
| POST | `/batch` | Analyse up to 10 stories |

Swagger docs at `/docs`.

---

## Deploy to Railway (10 minutes)

1. Push this folder to a GitHub repo called `econlens-api`
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Select the `econlens-api` repo
4. Add these environment variables:

```
GROQ_API_KEY      = gsk_...         (from console.groq.com — free)
GNEWS_API_KEY     = ...             (from gnews.io — free, 100 req/day)
MODEL_NAME        = llama-3.1-8b-instant
FRONTEND_URL      = https://yourusername.github.io
CACHE_TTL_SECONDS = 1800
```

5. Deploy — Railway auto-detects Python, installs requirements, starts the server
6. Your API is live at `https://econlens-api.up.railway.app`

---

## Run locally

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in your keys
uvicorn main:app --reload
# API at http://localhost:8000
# Docs at http://localhost:8000/docs
```

---

## How feed caching works

- `/feed` returns cached stories for 30 minutes
- After 30 min, next request auto-refreshes
- Force refresh anytime: `/feed?refresh=true`
- This keeps GNews API usage well within 100 req/day free limit
