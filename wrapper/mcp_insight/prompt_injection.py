"""
mcp_insight.prompt_injection

Passive-tap detection of prompt injection attempts delivered through MCP
JSON-RPC payloads (tool descriptions, tool call results, error messages).
This is taxonomy category 28 -- kept deliberately separate from the 27
functional-fault categories: it's adversarial, not a fault, so it never
feeds into health-score denominators or the fault classifier.

Detect-only, never modifies or blocks traffic: the wrapper sits inline in
the stdio path and technically *could* strip/block flagged content, but
this module only ever tags and reports -- every other feature in this
system is passive observability, and a false positive here must never be
able to break a live tool call.

Only small derived signals are ever attached to an event (matched pattern
names, a short preview, z-scores) -- never the full flagged text -- same
privacy posture as schema_violation/retrieval_signals elsewhere in this
wrapper.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from typing import Any, Optional

IMPERATIVE_PATTERNS = [
    r"\b(ignore|disregard|forget)\s+(the\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|context)",
    r"\byou\s+(must|should|will)\s+now\b",
    r"\bas\s+the\s+(ai|assistant|model)\b.{0,40}\b(you|your)\b",
    r"\bdo\s+not\s+(tell|inform|mention|show)\s+the\s+user\b",
    r"\bbefore\s+(responding|replying|answering)\b.{0,40}\b(first|also)\b",
    r"\balways\s+(call|invoke|use|include)\b",
    r"\bnew\s+(instructions?|system\s+prompt|directive)\b",
]

ROLE_SPOOF_PATTERNS = [
    r"\[\s*(system|admin|developer|root)\s*\]",
    r"\b(admin|developer|debug|god)\s+mode\b",
    r"\bas\s+(the\s+)?system\b",
    r"\boverride\s+(permissions?|restrictions?|safety)\b",
    r"\byou\s+are\s+now\s+(in|running)\b",
]

_EXFIL_VERBS = r"(include|append|send|forward|attach|embed|copy|reveal|output|print)"
_EXFIL_NOUNS = r"(api[\s_-]?key|token|credential|secret|password|env(ironment)?\s+var|conversation\s+history|system\s+prompt|prior\s+messages?)"
EXFIL_PATTERNS = [rf"\b{_EXFIL_VERBS}\b.{{0,50}}\b{_EXFIL_NOUNS}\b"]

OBFUSCATION_PATTERNS = {
    "base64_blob": r"[A-Za-z0-9+/]{40,}={0,2}",
    "zero_width": r"[​‌‍⁠﻿]",
    "html_comment": r"<!--.*?-->",
    "markdown_comment": r"\[//\]:\s*#",
    "homoglyph_hint": r"[а-яА-Я].*[a-zA-Z]|[a-zA-Z].*[а-яА-Я]",
}

_PATTERN_GROUPS: dict[str, list[re.Pattern]] = {
    "imperative_to_model": [re.compile(p, re.IGNORECASE) for p in IMPERATIVE_PATTERNS],
    "role_authority_spoofing": [re.compile(p, re.IGNORECASE) for p in ROLE_SPOOF_PATTERNS],
    "exfiltration_trigger": [re.compile(p, re.IGNORECASE) for p in EXFIL_PATTERNS],
    "encoding_obfuscation": [re.compile(p, re.DOTALL) for name, p in OBFUSCATION_PATTERNS.items()],
}

MIN_BASELINE_SAMPLES = 20
STRUCTURAL_ZSCORE_THRESHOLD = 3.0


def shannon_entropy(text: str) -> float:
    if not text:
        return 0.0
    counts = Counter(text)
    length = len(text)
    return -sum((c / length) * math.log2(c / length) for c in counts.values())


def _flatten_to_text(value: Any, max_len: int = 4000) -> str:
    """Flattens a result/error payload to a single string for pattern
    scanning, capped so a huge payload can't make scanning expensive."""
    if isinstance(value, str):
        return value[:max_len]
    try:
        return json.dumps(value, default=str)[:max_len]
    except (TypeError, ValueError):
        return str(value)[:max_len]


def count_pattern_hits(text: str) -> int:
    """Total number of individual regex matches across all groups --
    distinct from `scan_text`'s deduplicated subtype list. A single
    subtype (e.g. imperative_to_model) has multiple patterns, and two
    different patterns both matching within that one category is a much
    stronger signal than either alone, so the precision gate counts raw
    matches, not distinct categories."""
    if not text:
        return 0
    return sum(1 for patterns in _PATTERN_GROUPS.values() for p in patterns if p.search(text))


def scan_text(text: str) -> list[str]:
    """Returns the list of taxonomy-28 subtypes whose patterns matched
    this text (deduplicated, order-stable)."""
    if not text:
        return []
    hits: list[str] = []
    for subtype, patterns in _PATTERN_GROUPS.items():
        if any(p.search(text) for p in patterns):
            hits.append(subtype)
    return hits


class FieldBaseline:
    """Online (Welford) mean/variance tracker for one numeric field --
    used to flag structural anomalies (28.4) against a field's own
    history rather than a fixed threshold, since "normal" length/entropy
    varies enormously per tool."""

    def __init__(self) -> None:
        self.n = 0
        self._mean = 0.0
        self._m2 = 0.0

    def update(self, value: float) -> None:
        self.n += 1
        delta = value - self._mean
        self._mean += delta / self.n
        delta2 = value - self._mean
        self._m2 += delta * delta2

    @property
    def mean(self) -> float:
        return self._mean

    @property
    def stddev(self) -> float:
        if self.n < 2:
            return 0.0
        return math.sqrt(self._m2 / (self.n - 1))

    def zscore(self, value: float) -> Optional[float]:
        if self.n < MIN_BASELINE_SAMPLES or self.stddev == 0:
            return None
        return (value - self._mean) / self.stddev


class PromptInjectionDetector:
    """Per-session detector: keyword pattern scanning (always active) plus
    a per-tool structural-anomaly baseline (active once enough samples
    have been seen for that tool) on tool call results."""

    def __init__(self) -> None:
        self._length_baselines: dict[str, FieldBaseline] = {}
        self._entropy_baselines: dict[str, FieldBaseline] = {}

    def scan_tool_description(self, tool_name: str, description: Optional[str]) -> Optional[dict]:
        if not description:
            return None
        hits = scan_text(description)
        # Same precision gate as _scan_field: descriptions are checked
        # once (no structural baseline makes sense for a single sample),
        # so require 2+ independent pattern hits to report -- a single
        # match (e.g. "you must provide a valid path") is too weak alone.
        if count_pattern_hits(description) < 2:
            return None
        return {
            "subtypes": hits,
            "confidence_source": "keyword",
            "source_field": "tool_description",
            "preview": description[:160],
        }

    def scan_call_result(self, tool_name: str, result: Any) -> Optional[dict]:
        return self._scan_field(tool_name, result, "result")

    def scan_error(self, tool_name: str, error: Any) -> Optional[dict]:
        signal = self._scan_field(tool_name, error, "error")
        if signal and "error_channel_injection" not in signal["subtypes"]:
            # 28.5 isn't its own pattern set -- it's a coverage tag noting
            # *where* the payload was found, since error channels are an
            # underscanned vector in most pipelines.
            signal["subtypes"].append("error_channel_injection")
        return signal

    def _scan_field(self, tool_name: str, value: Any, field_label: str) -> Optional[dict]:
        if value is None:
            return None
        text = _flatten_to_text(value)
        if not text:
            return None

        hits = scan_text(text)

        length_baseline = self._length_baselines.setdefault(f"{tool_name}:{field_label}", FieldBaseline())
        entropy_baseline = self._entropy_baselines.setdefault(f"{tool_name}:{field_label}", FieldBaseline())
        length, entropy = len(text), shannon_entropy(text)
        z_length = length_baseline.zscore(length)
        z_entropy = entropy_baseline.zscore(entropy)
        structural_anomaly = (z_length is not None and abs(z_length) > STRUCTURAL_ZSCORE_THRESHOLD) or (
            z_entropy is not None and abs(z_entropy) > STRUCTURAL_ZSCORE_THRESHOLD
        )
        # Update baselines after scoring against them, not before.
        length_baseline.update(length)
        entropy_baseline.update(entropy)

        if not hits and not structural_anomaly:
            return None

        # Precision gate: require 2+ pattern hits, or 1+ hit plus a
        # structural anomaly, or a structural anomaly with no keyword hit
        # at all (novel/obfuscated payloads) -- a single keyword hit alone
        # (e.g. "you must provide a valid file path" in an ordinary
        # description) is too weak to report on its own.
        if count_pattern_hits(text) < 2 and not structural_anomaly:
            return None

        return {
            "subtypes": hits if hits else ["structural_anomaly"],
            "confidence_source": "keyword" if hits else "structural",
            "source_field": field_label,
            "preview": text[:160],
            "z_length": round(z_length, 2) if z_length is not None else None,
            "z_entropy": round(z_entropy, 2) if z_entropy is not None else None,
        }
