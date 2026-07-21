from __future__ import annotations

"""
LLM fallback classification: only invoked when TF-IDF confidence is below
LOW_CONFIDENCE_THRESHOLD. Sends the taxonomy + query text to Claude and
asks it to pick the best-matching subcategory. Optional -- if
ANTHROPIC_API_KEY isn't set, callers just keep the TF-IDF result.
"""
import json
import os

import httpx

from .taxonomy_data import TAXONOMY, dominant

_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
_MODEL = os.environ.get("ANTHROPIC_CLASSIFY_MODEL", "claude-haiku-4-5-20251001")
_ENABLED = bool(_API_KEY)

_TAXONOMY_LIST = "\n".join(f"- {row['category']} / {row['subcategory']}: {row['text']}" for row in TAXONOMY)
_BY_KEY = {(row["category"], row["subcategory"]): row for row in TAXONOMY}


async def classify_with_llm(text: str) -> dict | None:
    """Returns a result dict shaped like a TF-IDF ClassifyResult, or None
    if disabled/unavailable -- never raises, caller keeps the TF-IDF
    result as-is on failure."""
    if not _ENABLED:
        return None

    prompt = (
        "Classify this MCP server fault against exactly one taxonomy entry below. "
        "Reply with ONLY JSON: {\"category\": \"...\", \"subcategory\": \"...\"}.\n\n"
        f"Taxonomy:\n{_TAXONOMY_LIST}\n\nFault: {text}"
    )
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": _API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": _MODEL,
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            body = resp.json()
            raw = body["content"][0]["text"]
            picked = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
            row = _BY_KEY.get((picked["category"], picked["subcategory"]))
            if row is None:
                return None
            return {
                "category": row["category"],
                "subcategory": row["subcategory"],
                "confidence": None,  # LLM picks don't carry a TF-IDF-style score
                "dominant_severity": dominant(row["severity"]),
                "dominant_effort": dominant(row["effort"]),
                "practitioner_confirmed_pct": row["confirmed_pct"],
                "source": "llm",
            }
    except Exception:
        return None
