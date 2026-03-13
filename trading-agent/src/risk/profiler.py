"""
Risk Profiler — Sprint 1.5.

Converts a 6-dimension questionnaire into a normalised risk score [0, 1]
and a category label used to drive AgentConfig parameter derivation.

Questionnaire dimensions:
  investment_horizon  : SHORT | MEDIUM | LONG
  risk_tolerance      : CONSERVATIVE | MODERATE | AGGRESSIVE
  experience_level    : BEGINNER | INTERMEDIATE | EXPERT
  income_stability    : UNSTABLE | VARIABLE | STABLE
  loss_capacity       : LOW | MEDIUM | HIGH
  primary_goal        : CAPITAL_PRESERVATION | INCOME | GROWTH | SPECULATION

Score scale:
  0.00 – 0.25  → CONSERVATIVE
  0.25 – 0.50  → MODERATE
  0.50 – 0.75  → AGGRESSIVE
  0.75 – 1.00  → SPECULATIVE
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# ── Scoring weights ────────────────────────────────────────────────────────────
# Each dimension contributes a signed delta to the raw score.
# Weights are designed so that min_raw = -1.2 and max_raw = +1.2,
# which maps cleanly onto the [0, 1] normalised output.

_WEIGHTS: dict[str, dict[str, float]] = {
    "investment_horizon": {
        "SHORT":  -0.2,
        "MEDIUM":  0.0,
        "LONG":   +0.2,
    },
    "risk_tolerance": {
        "CONSERVATIVE": -0.3,
        "MODERATE":      0.0,
        "AGGRESSIVE":   +0.3,
    },
    "experience_level": {
        "BEGINNER":      -0.2,
        "INTERMEDIATE":   0.0,
        "EXPERT":        +0.2,
    },
    "income_stability": {
        "UNSTABLE": -0.2,
        "VARIABLE":  0.0,
        "STABLE":   +0.1,
    },
    "loss_capacity": {
        "LOW":    -0.2,
        "MEDIUM":  0.0,
        "HIGH":   +0.2,
    },
    "primary_goal": {
        "CAPITAL_PRESERVATION": -0.3,
        "INCOME":               -0.1,
        "GROWTH":               +0.1,
        "SPECULATION":          +0.3,
    },
}

# Pre-compute normalization bounds
_MIN_RAW: float = sum(min(v.values()) for v in _WEIGHTS.values())  # -1.2
_MAX_RAW: float = sum(max(v.values()) for v in _WEIGHTS.values())  # +1.1

# (threshold_exclusive, category_label)
_CATEGORY_THRESHOLDS = [
    (0.25, "CONSERVATIVE"),
    (0.50, "MODERATE"),
    (0.75, "AGGRESSIVE"),
    (1.01, "SPECULATIVE"),
]

VALID_ANSWERS: dict[str, list[str]] = {
    dim: list(opts.keys()) for dim, opts in _WEIGHTS.items()
}


# ── Result ─────────────────────────────────────────────────────────────────────

@dataclass
class RiskScoreResult:
    risk_score:    float         # [0.0, 1.0]
    risk_category: str           # CONSERVATIVE | MODERATE | AGGRESSIVE | SPECULATIVE
    raw_score:     float         # pre-normalisation (debug)
    answers:       dict[str, str]  # normalised echo of inputs


# ── Public API ─────────────────────────────────────────────────────────────────

def score_profile(answers: dict[str, str]) -> RiskScoreResult:
    """
    Compute a risk score from questionnaire answers.

    Missing dimensions default to their neutral value (0.0 contribution).
    Answer strings are case-insensitive.

    Args:
        answers: {dimension: answer_string}

    Returns:
        RiskScoreResult with normalised score and category.
    """
    raw = 0.0
    normalised_answers: dict[str, str] = {}

    for dimension, opts in _WEIGHTS.items():
        raw_answer = answers.get(dimension, "")
        upper = raw_answer.upper()
        raw += opts.get(upper, 0.0)
        normalised_answers[dimension] = upper

    # Normalise to [0, 1]
    span = _MAX_RAW - _MIN_RAW
    score = float((raw - _MIN_RAW) / span) if span > 0 else 0.5
    score = max(0.0, min(1.0, score))

    # Classify
    category = "CONSERVATIVE"
    for threshold, label in _CATEGORY_THRESHOLDS:
        if score < threshold:
            category = label
            break

    return RiskScoreResult(
        risk_score    = round(score, 4),
        risk_category = category,
        raw_score     = round(raw, 4),
        answers       = normalised_answers,
    )


def validate_answers(answers: dict[str, Any]) -> list[str]:
    """
    Validate questionnaire answers.

    Returns:
        List of error strings.  Empty list means all answers are valid.
    """
    errors: list[str] = []
    for dimension, valid in VALID_ANSWERS.items():
        val = answers.get(dimension)
        if val is None:
            errors.append(f"Missing required field: '{dimension}'")
        elif str(val).upper() not in valid:
            errors.append(
                f"Invalid answer for '{dimension}': '{val}'. "
                f"Valid options: {valid}"
            )
    return errors
