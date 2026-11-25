"""
Baseline method: count hawkish and dovish phrases. No AI, fully transparent.

    score = (hawkish count - dovish count) / (hawkish count + dovish count)

which lies between -1 (all dovish) and +1 (all hawkish).

Weakness (on purpose, so the comparison with the LLM is fair): word counts
ignore context. "Inflation has eased" contains the hawkish-sounding word
"inflation" but is actually dovish. That is exactly where an LLM should help.
"""
from __future__ import annotations

import re

HAWKISH = [
    "raise the target range", "increase the target range", "raised the target range",
    "firming", "tightening", "tighten", "additional policy firming",
    "inflation remains elevated", "inflation remained elevated", "elevated inflation",
    "inflation pressures", "upside risks to inflation", "inflation risks",
    "strong", "robust", "solid pace", "tight labor market",
    "reduce its holdings", "reducing its holdings", "balance sheet reduction",
    "highly attentive to inflation risks", "returning inflation to its 2 percent",
]

DOVISH = [
    "lower the target range", "lowered the target range", "decrease the target range",
    "reduce the target range", "lower its target", "cut",
    "accommodative", "accommodation", "patient", "exceptionally low",
    "downside risks", "weakened", "weak", "weakness", "slack", "soft",
    "subdued", "low inflation", "inflation has eased", "moderated",
    "asset purchases", "purchase additional", "increase its holdings",
    "support the economy", "deteriorated", "contraction", "stress",
]


def _count(text: str, phrases: list[str]) -> int:
    t = text.lower()
    return sum(len(re.findall(r"\b" + re.escape(p) + r"\b", t)) for p in phrases)


def dictionary_score(text: str) -> dict:
    h, d = _count(text, HAWKISH), _count(text, DOVISH)
    score = (h - d) / (h + d) if (h + d) else 0.0
    return {"dict_score": score, "hawkish_count": h, "dovish_count": d}
