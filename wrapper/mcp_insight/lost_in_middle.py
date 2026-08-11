"""
mcp_insight.lost_in_middle

Best-effort detection of *risk factors* for "lost in the middle" context
degradation -- not a claim of proving the downstream LLM actually missed
something, since the wrapper has zero visibility into that model's
attention or reasoning. What it can honestly detect, from protocol
traffic alone, are the conditions the research literature ties to LITM
degradation:

- oversized or unranked context returned by a retrieval-shaped tool
  (accuracy on long-context tasks measurably degrades as retrieved-item
  count grows, especially past ~10-20 items, and worse when results
  aren't sorted by relevance)
- a result payload that's a statistical size outlier vs. that tool's own
  history (same z-score approach as prompt_injection.py's structural
  anomaly check)
- the same tool being called again with the same arguments shortly after
  a large prior result -- a real, protocol-visible signal that the first
  answer's context likely wasn't used effectively, whether because of
  LITM, poor ranking, or something else entirely; labeled as a risk
  factor, not a diagnosis.

Only small derived numbers are ever attached to an event -- never the
raw context content, same privacy posture as every other detector in
this wrapper.
"""
from __future__ import annotations

import json
import time
from typing import Any, Optional

from .prompt_injection import FieldBaseline
from .retrieval_signals import (
    extract_items_with_preview,
    extract_scores,
    find_result_list,
    looks_like_retrieval_tool,
)

LARGE_RESULT_COUNT_THRESHOLD = 15
SIZE_ZSCORE_THRESHOLD = 3.0
REPEATED_QUERY_WINDOW_S = 300.0
REPEATED_QUERY_MIN_PRIOR_CHARS = 2000
CHARS_PER_TOKEN_ESTIMATE = 4  # rough heuristic for English text
INPUT_PREVIEW_MAX_CHARS = 200
MAX_ITEMS_CAPTURED = 30  # cap on per-item score/preview array attached to a flagged event


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN_ESTIMATE)


def _flatten_to_text(value: Any, max_len: int = 20000) -> str:
    if isinstance(value, str):
        return value[:max_len]
    try:
        return json.dumps(value, default=str)[:max_len]
    except (TypeError, ValueError):
        return str(value)[:max_len]


def _stable_args_key(tool_name: str, arguments: Any) -> str:
    try:
        normalized = json.dumps(arguments, sort_keys=True, default=str)
    except (TypeError, ValueError):
        normalized = str(arguments)
    return f"{tool_name}:{normalized}"


class LostInMiddleDetector:
    """Per-session detector: a size baseline per tool, plus a short-lived
    memory of recent (tool, arguments) pairs for repeated-query detection."""

    def __init__(self) -> None:
        self._size_baselines: dict[str, FieldBaseline] = {}
        self._recent_calls: dict[str, dict] = {}

    def check_call(self, tool_name: str, description: Optional[str], arguments: Any, result: Any) -> Optional[dict]:
        if result is None:
            return None
        text = _flatten_to_text(result)
        size = len(text)
        risk_factors: list[str] = []
        # Every check's actual value vs. its threshold, fired or not -- the
        # literal rule trace, not just the label, so a reader can audit
        # *why* (and why NOT) a factor fired without trusting a summary.
        decision_trail: list[dict] = []

        baseline = self._size_baselines.setdefault(tool_name, FieldBaseline())
        z_size = baseline.zscore(size)
        size_outlier_fired = z_size is not None and abs(z_size) > SIZE_ZSCORE_THRESHOLD and size > baseline.mean
        if size_outlier_fired:
            risk_factors.append("size_outlier")
        decision_trail.append({
            "check": "size_outlier",
            "fired": size_outlier_fired,
            "threshold": SIZE_ZSCORE_THRESHOLD,
            "actual": round(z_size, 2) if z_size is not None else None,
            "detail": f"response size {size} chars vs. this tool's rolling mean {round(baseline.mean, 1)} chars"
            if z_size is not None
            else "no baseline yet for this tool",
        })
        baseline.update(size)

        result_count: Optional[int] = None
        items_detail: list[dict] = []
        if looks_like_retrieval_tool(tool_name, description):
            items = find_result_list(result)
            if items is not None:
                result_count = len(items)
                large_result_fired = result_count > LARGE_RESULT_COUNT_THRESHOLD
                if large_result_fired:
                    risk_factors.append("large_result_set")
                decision_trail.append({
                    "check": "large_result_set",
                    "fired": large_result_fired,
                    "threshold": LARGE_RESULT_COUNT_THRESHOLD,
                    "actual": result_count,
                    "detail": f"{result_count} results returned, threshold is {LARGE_RESULT_COUNT_THRESHOLD}",
                })

                scores = extract_scores(items)
                unranked_fired = len(scores) >= 2 and scores != sorted(scores, reverse=True)
                if unranked_fired:
                    risk_factors.append("unranked_results")
                decision_trail.append({
                    "check": "unranked_results",
                    "fired": unranked_fired,
                    "threshold": "scores sorted descending",
                    "actual": scores[:MAX_ITEMS_CAPTURED] if scores else None,
                    "detail": "result scores are not in descending order" if unranked_fired
                    else ("result scores are properly ranked" if scores else "no per-item scores found"),
                })

                if risk_factors:
                    items_detail = extract_items_with_preview(items[:MAX_ITEMS_CAPTURED])

        args_key = _stable_args_key(tool_name, arguments)
        now = time.time()
        prior = self._recent_calls.get(args_key)
        repeated_fired = bool(
            prior
            and (now - prior["ts"]) < REPEATED_QUERY_WINDOW_S
            and prior["size"] > REPEATED_QUERY_MIN_PRIOR_CHARS
        )
        if repeated_fired:
            risk_factors.append("repeated_query_after_large_context")
        decision_trail.append({
            "check": "repeated_query_after_large_context",
            "fired": repeated_fired,
            "threshold": f"same args within {int(REPEATED_QUERY_WINDOW_S)}s of a prior result > {REPEATED_QUERY_MIN_PRIOR_CHARS} chars",
            "actual": f"{round(now - prior['ts'], 1)}s since prior call of {prior['size']} chars" if prior else "no prior call with these args",
        })
        self._recent_calls[args_key] = {"ts": now, "size": size}

        if not risk_factors:
            return None

        return {
            "risk_factors": risk_factors,
            "result_count": result_count,
            "approx_tokens": estimate_tokens(text),
            "z_size": round(z_size, 2) if z_size is not None else None,
            "decision_trail": decision_trail,
            "items": items_detail,
            "input_preview": _flatten_to_text(arguments, INPUT_PREVIEW_MAX_CHARS),
        }
