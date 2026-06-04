import re, time, json, os, asyncio
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from groq import Groq
from datetime import datetime, timezone

# ── Config ────────────────────────────────────────────────────────
GROQ_API_KEY  = os.environ.get("GROQ_API_KEY",  "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")
GNEWS_API_KEY = os.environ.get("GNEWS_API_KEY", "aebb24538d2cc54b74401f747d575822")
MODEL_NAME    = os.environ.get("MODEL_NAME",    "llama-3.1-8b-instant")
FRONTEND_URL  = os.environ.get("FRONTEND_URL",  "github.com/anoop006/ecolenss")
CACHE_TTL     = int(os.environ.get("CACHE_TTL_SECONDS", "1800"))  # 30 min default

client = Groq(api_key=GROQ_API_KEY)

# ── App ───────────────────────────────────────────────────────────
app = FastAPI(
    title="EconLens API",
    description="Business news through economics, game theory & geopolitics. Keys live here — visitors need none.",
    version="3.0.0"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Lenses ────────────────────────────────────────────────────────
LENSES = {
    "prisoners_dilemma":    {"label":"Prisoner's Dilemma",     "desc":"Strategic interdependence where rational self-interest leads to collectively worse outcomes."},
    "principal_agent":      {"label":"Principal-Agent Problem", "desc":"Misaligned incentives between a principal (owner/board) and an agent (manager/employee)."},
    "nash_equilibrium":     {"label":"Nash Equilibrium",        "desc":"Stable state where no player improves by changing strategy, given what others are doing."},
    "market_concentration": {"label":"Market Concentration",    "desc":"How power is distributed — monopoly, duopoly, oligopoly — and its competitive effects."},
    "modern_econ":          {"label":"Modern Economic Theory",  "desc":"Behavioural economics, information asymmetry, network effects, institutional factors."},
    "market_types":         {"label":"Market Types",            "desc":"Perfect competition, monopolistic competition, oligopoly, or monopoly — and what it means here."},
}

# ── Prompts ───────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are an expert economics, game theory, and geopolitical analyst for EconLens — an Indian business news platform.
Cut through social media noise by explaining business news through rigorous economic, strategic, and geopolitical frameworks.

GEOPOLITICS IS THE UMBRELLA. Consider these angles first:
- Trade wars & tariffs
- India-China-US triangle
- Sanctions & supply chains
- Currency & forex pressure

Return ONLY valid JSON — no markdown, no backticks:
{
  "headline": "One sharp sentence capturing the core economic tension",
  "geo_umbrella": {
    "context": "2-3 sentences on the geopolitical backdrop.",
    "risk_level": "Low | Medium | High",
    "risk_reason": "One sentence explaining the risk rating.",
    "angles": ["only the relevant angles from the 4 listed"]
  },
  "lenses": [
    {"key": "lens_key", "insight": "2-3 sharp sentences. Name the mechanism clearly."}
  ],
  "verdict": "One bold shareable sentence — why this outcome was economically inevitable."
}"""

FEED_PROMPT = """You are an economics analyst for EconLens, an Indian business news platform.
Analyse this headline quickly. Return ONLY valid JSON — no markdown:
{
  "headline": "One sharp economic tension sentence",
  "geo_umbrella": {
    "context": "1-2 sentences on geopolitical backdrop.",
    "risk_level": "Low | Medium | High",
    "risk_reason": "One sentence.",
    "angles": ["Trade wars & tariffs | India-China-US triangle | Sanctions & supply chains | Currency & forex pressure"]
  },
  "lenses": [
    {"key": "prisoners_dilemma",    "insight": "1-2 sentences."},
    {"key": "nash_equilibrium",     "insight": "1-2 sentences."},
    {"key": "market_concentration", "insight": "1-2 sentences."}
  ],
  "verdict": "One bold shareable sentence."
}"""

# ── Feed cache ────────────────────────────────────────────────────
_cache: dict = {"stories": [], "fetched_at": None}

# ── Schemas ───────────────────────────────────────────────────────
class AnalyseRequest(BaseModel):
    story: str
    active_lenses: Optional[List[str]] = None

# ── Helpers ───────────────────────────────────────────────────────
def clean_json(text: str) -> dict:
    text = re.sub(r"```json|```", "", text).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON in response")
    return json.loads(re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", match.group(0)))


def call_groq(prompt: str, system: str = None, max_tokens: int = 1800) -> dict:
    for attempt in range(1, 4):
        try:
            r = client.chat.completions.create(
                model=MODEL_NAME,
                temperature=0.3,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system or SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt}
                ]
            )
            return clean_json(r.choices[0].message.content)
        except Exception as e:
            if ("429" in str(e) or "rate" in str(e).lower()) and attempt < 3:
                time.sleep(30)
            else:
                raise


async def fetch_gnews(query: str, max_items: int = 6, country: str = None) -> list:
    if not GNEWS_API_KEY:
        return []
    params = {"q": query, "lang": "en", "max": max_items, "sortby": "publishedAt", "apikey": GNEWS_API_KEY}
    if country:
        params["country"] = country
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get("https://gnews.io/api/v4/search", params=params)
            return r.json().get("articles", []) if r.is_success else []
    except Exception:
        return []


async def fetch_all_headlines() -> list:
    india, globe = await asyncio.gather(
        fetch_gnews("india business economy", max_items=6, country="in"),
        fetch_gnews("business economy trade",  max_items=6),
    )
    articles, seen = [], set()
    for a in [*[{**x, "flag":"🇮🇳"} for x in india], *[{**x, "flag":"🌐"} for x in globe]]:
        t = a.get("title", "")
        if t and t not in seen:
            seen.add(t)
            articles.append(a)
    return articles[:10]


async def analyse_headline(article: dict) -> dict:
    story = f"{article.get('title','')}. {article.get('description','')}"
    loop  = asyncio.get_event_loop()
    src   = article.get("source", {}).get("name", "")
    try:
        result = await loop.run_in_executor(
            None, lambda: call_groq(f'Analyse: "{story}"\n\nJSON only.', system=FEED_PROMPT, max_tokens=700)
        )
        return {**result, "source": src, "flag": article.get("flag","🌐"),
                "link": article.get("url",""), "pub_date": article.get("publishedAt",""), "_pending": False}
    except Exception:
        return {"headline": article.get("title",""), "source": src, "flag": article.get("flag","🌐"),
                "link": article.get("url",""), "pub_date": article.get("publishedAt",""),
                "geo_umbrella": None, "lenses": [], "verdict": "", "_pending": True}


async def build_feed() -> list:
    articles = await fetch_all_headlines()
    if not articles:
        return []
    top, rest = articles[:2], articles[2:]
    analysed  = await asyncio.gather(*[analyse_headline(a) for a in top])
    pending   = [{"headline": a.get("title",""), "source": a.get("source",{}).get("name",""),
                  "flag": a.get("flag","🌐"), "link": a.get("url",""),
                  "pub_date": a.get("publishedAt",""), "geo_umbrella": None,
                  "lenses": [], "verdict": "", "_pending": True} for a in rest]
    return list(analysed) + pending

# ── Routes ────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"name": "EconLens API", "version": "3.0.0", "model": MODEL_NAME,
            "status": "running", "docs": "/docs",
            "endpoints": ["/", "/lenses", "/feed", "/analyse", "/batch"]}


@app.get("/health")
def health():
    return {"status": "ok", "groq": bool(GROQ_API_KEY), "gnews": bool(GNEWS_API_KEY)}


@app.get("/lenses")
def get_lenses():
    return {"lenses": [{"key": k, **v} for k, v in LENSES.items()]}


@app.get("/feed")
async def get_feed(refresh: bool = False):
    """
    Returns today's analysed business news.
    Cached for 30 min — pass ?refresh=true to force a fresh fetch.
    No API key needed from the frontend.
    """
    global _cache
    now = datetime.now(timezone.utc)
    age = (_cache["fetched_at"] and (now - _cache["fetched_at"]).total_seconds()) or None
    is_stale = age is None or age > CACHE_TTL

    if not refresh and not is_stale and _cache["stories"]:
        return {"stories": _cache["stories"], "cached": True,
                "fetched_at": _cache["fetched_at"].isoformat(),
                "cache_age_minutes": round(age / 60, 1)}

    try:
        stories = await build_feed()
        _cache  = {"stories": stories, "fetched_at": now}
        return {"stories": stories, "cached": False,
                "fetched_at": now.isoformat(), "total": len(stories)}
    except Exception as e:
        raise HTTPException(503, f"Feed unavailable: {e}")


@app.post("/analyse")
def analyse(req: AnalyseRequest):
    """
    Analyse a news story. No API key needed from the frontend.
    """
    if not req.story.strip():
        raise HTTPException(400, "story cannot be empty")
    active  = req.active_lenses or list(LENSES.keys())
    invalid = [k for k in active if k not in LENSES]
    if invalid:
        raise HTTPException(400, f"Unknown lens keys: {invalid}")
    lens_lines = "\n".join([f"- {k}: {LENSES[k]['label']} — {LENSES[k]['desc']}" for k in active])
    try:
        return call_groq(f"Analyse:\n\n{req.story}\n\nLenses:\n{lens_lines}\n\nJSON only.")
    except Exception as e:
        raise HTTPException(503, str(e))


@app.post("/batch")
def batch(stories: List[str], active_lenses: Optional[List[str]] = None):
    """Analyse up to 10 stories at once."""
    if not stories:        raise HTTPException(400, "stories list cannot be empty")
    if len(stories) > 10:  raise HTTPException(400, "Max 10 stories per batch")
    results = []
    for s in stories:
        try:
            results.append({"story": s[:120], "result": analyse(AnalyseRequest(story=s, active_lenses=active_lenses)), "error": None})
        except Exception as e:
            results.append({"story": s[:120], "result": None, "error": str(e)})
        time.sleep(2)
    return {"count": len(results), "results": results}
