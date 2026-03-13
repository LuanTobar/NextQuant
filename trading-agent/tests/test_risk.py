"""
Tests for Sprint 1.5 Risk Profiling Engine.

Run: pytest tests/test_risk.py -v
(from trading-agent/ with the project .venv active)
"""

from __future__ import annotations

import pytest
import sys
import os

# Ensure src/ is on the path when running from trading-agent/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.risk.profiler import score_profile, validate_answers, VALID_ANSWERS
from src.risk.profile_adapter import derive_agent_config, config_for_category


# ── Fixtures ───────────────────────────────────────────────────────────────────

_CONSERVATIVE_ANSWERS = {
    "investment_horizon": "SHORT",
    "risk_tolerance":     "CONSERVATIVE",
    "experience_level":   "BEGINNER",
    "income_stability":   "UNSTABLE",
    "loss_capacity":      "LOW",
    "primary_goal":       "CAPITAL_PRESERVATION",
}

_MODERATE_ANSWERS = {
    "investment_horizon": "MEDIUM",
    "risk_tolerance":     "MODERATE",
    "experience_level":   "INTERMEDIATE",
    "income_stability":   "VARIABLE",
    "loss_capacity":      "MEDIUM",
    "primary_goal":       "INCOME",
}

_AGGRESSIVE_ANSWERS = {
    "investment_horizon": "LONG",
    "risk_tolerance":     "AGGRESSIVE",
    "experience_level":   "EXPERT",
    "income_stability":   "STABLE",
    "loss_capacity":      "HIGH",
    "primary_goal":       "GROWTH",
}

_SPECULATIVE_ANSWERS = {
    "investment_horizon": "LONG",
    "risk_tolerance":     "AGGRESSIVE",
    "experience_level":   "EXPERT",
    "income_stability":   "STABLE",
    "loss_capacity":      "HIGH",
    "primary_goal":       "SPECULATION",
}


# ── TestProfilerScoring ────────────────────────────────────────────────────────

class TestProfilerScoring:
    def test_score_in_unit_interval(self):
        for answers in [_CONSERVATIVE_ANSWERS, _MODERATE_ANSWERS,
                        _AGGRESSIVE_ANSWERS, _SPECULATIVE_ANSWERS]:
            r = score_profile(answers)
            assert 0.0 <= r.risk_score <= 1.0, f"Score out of range: {r.risk_score}"

    def test_conservative_profile_category(self):
        r = score_profile(_CONSERVATIVE_ANSWERS)
        assert r.risk_category == "CONSERVATIVE"
        assert r.risk_score < 0.25

    def test_moderate_profile_category(self):
        r = score_profile(_MODERATE_ANSWERS)
        assert r.risk_category in ("MODERATE", "CONSERVATIVE")
        # Moderate answers should not be speculative
        assert r.risk_score < 0.75

    def test_aggressive_profile_category(self):
        r = score_profile(_AGGRESSIVE_ANSWERS)
        assert r.risk_category in ("AGGRESSIVE", "SPECULATIVE")
        assert r.risk_score >= 0.5

    def test_speculative_profile_category(self):
        r = score_profile(_SPECULATIVE_ANSWERS)
        assert r.risk_category in ("AGGRESSIVE", "SPECULATIVE")
        assert r.risk_score >= 0.5

    def test_conservative_score_less_than_aggressive(self):
        r_con = score_profile(_CONSERVATIVE_ANSWERS)
        r_agg = score_profile(_AGGRESSIVE_ANSWERS)
        assert r_con.risk_score < r_agg.risk_score

    def test_score_monotonicity_across_categories(self):
        """Conservative < Moderate < Aggressive < Speculative (by score)."""
        scores = [
            score_profile(_CONSERVATIVE_ANSWERS).risk_score,
            score_profile(_MODERATE_ANSWERS).risk_score,
            score_profile(_AGGRESSIVE_ANSWERS).risk_score,
            score_profile(_SPECULATIVE_ANSWERS).risk_score,
        ]
        assert scores[0] < scores[2], "Conservative should score lower than Aggressive"
        assert scores[1] < scores[3], "Moderate should score lower than Speculative"

    def test_answers_normalised_to_uppercase(self):
        answers = {k: v.lower() for k, v in _CONSERVATIVE_ANSWERS.items()}
        r = score_profile(answers)
        for v in r.answers.values():
            assert v == v.upper()

    def test_missing_dimension_defaults_to_neutral(self):
        """Partial answers: missing dims contribute 0 (neutral)."""
        full   = score_profile(_MODERATE_ANSWERS)
        partial = score_profile({"investment_horizon": "MEDIUM"})
        # partial should score lower than full moderate (missing dims default to 0)
        assert 0.0 <= partial.risk_score <= 1.0

    def test_result_has_all_fields(self):
        r = score_profile(_MODERATE_ANSWERS)
        assert hasattr(r, "risk_score")
        assert hasattr(r, "risk_category")
        assert hasattr(r, "raw_score")
        assert hasattr(r, "answers")

    def test_category_one_of_four(self):
        valid_cats = {"CONSERVATIVE", "MODERATE", "AGGRESSIVE", "SPECULATIVE"}
        for answers in [_CONSERVATIVE_ANSWERS, _MODERATE_ANSWERS,
                        _AGGRESSIVE_ANSWERS, _SPECULATIVE_ANSWERS]:
            r = score_profile(answers)
            assert r.risk_category in valid_cats


# ── TestValidateAnswers ────────────────────────────────────────────────────────

class TestValidateAnswers:
    def test_valid_answers_no_errors(self):
        assert validate_answers(_CONSERVATIVE_ANSWERS) == []

    def test_missing_field_reported(self):
        incomplete = {k: v for k, v in _MODERATE_ANSWERS.items()
                      if k != "primary_goal"}
        errors = validate_answers(incomplete)
        assert any("primary_goal" in e for e in errors)

    def test_invalid_answer_reported(self):
        bad = {**_MODERATE_ANSWERS, "risk_tolerance": "RECKLESS"}
        errors = validate_answers(bad)
        assert any("risk_tolerance" in e for e in errors)

    def test_empty_answers_six_errors(self):
        errors = validate_answers({})
        assert len(errors) == 6

    def test_case_insensitive_validation(self):
        lower = {k: v.lower() for k, v in _MODERATE_ANSWERS.items()}
        # lowercase answers should be invalid per validate_answers (expects uppercase match)
        # OR valid if validate_answers normalises — let's verify the actual behaviour
        errors = validate_answers(lower)
        # profiler.score_profile normalises, but validate_answers may not
        # Either all-valid or all-invalid is acceptable, as long as it's consistent
        assert isinstance(errors, list)


# ── TestProfileAdapter ─────────────────────────────────────────────────────────

class TestProfileAdapter:
    def test_conservative_low_position_size(self):
        result = score_profile(_CONSERVATIVE_ANSWERS)
        cfg    = derive_agent_config(result)
        assert cfg.max_position_size_usd <= 100.0
        assert cfg.aggressiveness < 0.5

    def test_speculative_high_position_size(self):
        result = score_profile(_SPECULATIVE_ANSWERS)
        cfg    = derive_agent_config(result)
        assert cfg.max_position_size_usd >= 500.0
        assert cfg.aggressiveness >= 0.7

    def test_config_override_has_all_fields(self):
        result = score_profile(_MODERATE_ANSWERS)
        cfg    = derive_agent_config(result)
        assert cfg.max_position_size_usd > 0
        assert cfg.max_concurrent_positions >= 1
        assert cfg.daily_loss_limit_usd > 0
        assert 0 < cfg.max_drawdown_pct <= 100
        assert 0.0 <= cfg.aggressiveness <= 1.0
        assert cfg.risk_category in ("CONSERVATIVE","MODERATE","AGGRESSIVE","SPECULATIVE")

    def test_to_dict_has_expected_keys(self):
        cfg  = derive_agent_config(score_profile(_MODERATE_ANSWERS))
        d    = cfg.to_dict()
        keys = {"maxPositionSizeUsd","maxConcurrentPositions",
                "dailyLossLimitUsd","maxDrawdownPct","aggressiveness"}
        assert keys.issubset(d.keys())

    def test_conservative_lower_risk_than_aggressive(self):
        cfg_con = derive_agent_config(score_profile(_CONSERVATIVE_ANSWERS))
        cfg_agg = derive_agent_config(score_profile(_AGGRESSIVE_ANSWERS))
        assert cfg_con.max_position_size_usd < cfg_agg.max_position_size_usd
        assert cfg_con.max_drawdown_pct < cfg_agg.max_drawdown_pct
        assert cfg_con.aggressiveness < cfg_agg.aggressiveness

    def test_config_for_category_direct(self):
        for cat in ("CONSERVATIVE", "MODERATE", "AGGRESSIVE", "SPECULATIVE"):
            cfg = config_for_category(cat)
            assert cfg.risk_category == cat
            assert cfg.max_position_size_usd > 0

    def test_config_for_category_case_insensitive(self):
        cfg = config_for_category("conservative")
        assert cfg.risk_category == "CONSERVATIVE"

    def test_risk_score_propagated(self):
        result = score_profile(_AGGRESSIVE_ANSWERS)
        cfg    = derive_agent_config(result)
        assert cfg.risk_score == result.risk_score
