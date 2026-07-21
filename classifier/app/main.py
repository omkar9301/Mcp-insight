"""
mcp_insight classifier service.

Matches free-text descriptions of captured faults (e.g. a schema violation
message, a protocol error, a timeout description) against the 27-category
real MCP fault taxonomy using TF-IDF + cosine similarity -- self-contained,
no external embedding API required to deploy.

For production-scale semantic matching, swap `_vectorize` to call Bedrock
Titan/Cohere embeddings and replace the sklearn index with MongoDB Atlas
Vector Search -- the /v1/classify contract below does not need to change.
"""
from __future__ import annotations

import os
import time
from collections import defaultdict, deque

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .llm_fallback import classify_with_llm
from .taxonomy_data import TAXONOMY, dominant

app = FastAPI(title="MCP Insight Classifier")

_origins = os.environ.get("DASHBOARD_ORIGINS", "http://localhost:5173,http://localhost:4173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

_API_KEY = os.environ.get("MCP_INSIGHT_API_KEY", "")


async def require_api_key(authorization: str | None = Header(default=None)) -> None:
    """Same shared static API key as the ingestion service (deliberately
    the same env var/secret) -- classifier is an internal service, not
    meant to be reachable except from ingestion or an authenticated caller."""
    if not _API_KEY:
        return
    if not authorization or not authorization.startswith("Bearer ") or authorization[len("Bearer "):] != _API_KEY:
        raise HTTPException(status_code=401, detail="Missing or invalid API key")


_RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_CLASSIFY_PER_MINUTE", "300"))
_hits: dict[str, deque] = defaultdict(deque)


async def enforce_rate_limit(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    hits = _hits[client_ip]
    while hits and now - hits[0] > 60.0:
        hits.popleft()
    if len(hits) >= _RATE_LIMIT_PER_MINUTE:
        raise HTTPException(status_code=429, detail=f"Rate limit exceeded ({_RATE_LIMIT_PER_MINUTE}/min)")
    hits.append(now)


_vectorizer = TfidfVectorizer(stop_words="english")
_corpus = [row["text"] for row in TAXONOMY]
_matrix = _vectorizer.fit_transform(_corpus)

LOW_CONFIDENCE_THRESHOLD = 0.15  # below this, flag for LLM fallback / human review


class ClassifyRequest(BaseModel):
    text: str
    top_k: int = 3


class ClassifyResult(BaseModel):
    category: str
    subcategory: str
    confidence: float | None
    dominant_severity: str | None
    dominant_effort: str | None
    practitioner_confirmed_pct: float | None
    source: str = "tfidf"


class ClassifyResponse(BaseModel):
    query: str
    low_confidence: bool
    results: list[ClassifyResult]


@app.post(
    "/v1/classify",
    response_model=ClassifyResponse,
    dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)],
)
async def classify(req: ClassifyRequest):
    query_vec = _vectorizer.transform([req.text])
    sims = cosine_similarity(query_vec, _matrix)[0]

    ranked = sorted(range(len(sims)), key=lambda i: sims[i], reverse=True)[: req.top_k]

    results = []
    for idx in ranked:
        row = TAXONOMY[idx]
        results.append(
            ClassifyResult(
                category=row["category"],
                subcategory=row["subcategory"],
                confidence=round(float(sims[idx]), 4),
                dominant_severity=dominant(row["severity"]),
                dominant_effort=dominant(row["effort"]),
                practitioner_confirmed_pct=row["confirmed_pct"],
            )
        )

    top_confidence = results[0].confidence if results else 0.0
    low_confidence = top_confidence < LOW_CONFIDENCE_THRESHOLD

    if low_confidence:
        llm_pick = await classify_with_llm(req.text)
        if llm_pick:
            results.insert(0, ClassifyResult(**llm_pick))

    return ClassifyResponse(
        query=req.text,
        low_confidence=low_confidence,
        results=results,
    )


@app.get("/v1/taxonomy", dependencies=[Depends(require_api_key)])
async def get_taxonomy():
    """Expose the full reference taxonomy, e.g. for the dashboard to render
    a static reference view independent of any live classification."""
    return {"taxonomy": TAXONOMY}


@app.get("/")
async def root():
    return {"service": "mcp-insight-classifier", "status": "ok", "categories_loaded": len(TAXONOMY)}
