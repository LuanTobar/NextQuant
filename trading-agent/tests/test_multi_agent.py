"""
Tests for Sprint 1.6 — Multi-agent E2E components.

Covers:
  - ResearchBrief / ResearchAnalyst  (python-ml)
  - RiskGuardian                     (trading-agent)
  - StrategyArchitect                (trading-agent) — mock-based
  - ExecutionSpecialist              (trading-agent) — mock-based
"""

import sys
import os
import asyncio
import unittest
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch

# ── path setup ───────────────────────────────────────────────────────────────
# trading-agent/   → imports as  src.*
# python-ml/src/   → imports as  research_brief (direct, avoids src/ namespace clash)
_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_here, ".."))                             # trading-agent/
sys.path.insert(0, os.path.join(_here, "..", "..", "python-ml", "src"))  # python-ml/src/

from src.risk_guardian import RiskGuardian, VetoResult
from src.execution_specialist import ExecutionSpecialist, ExecutionResult
from src.risk_manager import RiskManager, DailyRiskState
from src.position_tracker import PositionTracker
from src.brokers.base import AccountInfo, Position


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_config(
    allowed_symbols=None,
    max_position_size_usd=500.0,
    max_concurrent_positions=3,
    daily_loss_limit_usd=1000.0,
    max_drawdown_pct=20.0,
    aggressiveness=0.5,
    broker="alpaca",
):
    cfg = MagicMock()
    cfg.allowed_symbols = allowed_symbols or []
    cfg.max_position_size_usd = max_position_size_usd
    cfg.max_concurrent_positions = max_concurrent_positions
    cfg.daily_loss_limit_usd = daily_loss_limit_usd
    cfg.max_drawdown_pct = max_drawdown_pct
    cfg.aggressiveness = aggressiveness
    cfg.broker = broker
    return cfg


def _buy_signal(symbol="AAPL", price=100.0, alert_level="NORMAL", regime="SIDEWAYS"):
    return {
        "symbol": symbol,
        "signal": "BUY",
        "current_price": price,
        "alert_level": alert_level,
        "regime": regime,
        "confidence_low": price * 0.99,
        "confidence_high": price * 1.02,
    }


def _position(symbol="AAPL", qty=10, entry=100.0, current=105.0, mv=1050.0):
    return Position(
        symbol=symbol, quantity=qty,
        avg_entry_price=entry, current_price=current,
        market_value=mv, unrealized_pl=(current - entry) * qty,
        side="long",
    )


# ═════════════════════════════════════════════════════════════════════════════
# ResearchBrief tests
# ═════════════════════════════════════════════════════════════════════════════

class TestResearchBrief(unittest.TestCase):

    def setUp(self):
        # Import from python-ml/src/ (added directly to sys.path to avoid src/ namespace clash)
        from research_brief import ResearchAnalyst, ResearchBrief
        self.ResearchAnalyst = ResearchAnalyst
        self.ResearchBrief = ResearchBrief

    def _composite(self, **kwargs):
        base = {
            "symbol": "AAPL", "exchange": "US",
            "timestamp": "2026-01-01T00:00:00",
            "signal": "BUY", "current_price": 100.0,
            "predicted_close": 102.0,
            "ensemble_confidence": 0.75,
            "ensemble_expected_return": 0.02,
            "regime": "BULL_QUIET", "volatility": 10.0,
            "causal_effect": 0.5, "causal_n_significant": 3,
        }
        base.update(kwargs)
        return base

    def test_brief_normal_no_anomaly(self):
        analyst = self.ResearchAnalyst()
        brief = analyst.build_brief(self._composite())
        self.assertEqual(brief.alert_level, "NORMAL")
        self.assertEqual(brief.market_sentiment, "BULLISH")
        self.assertFalse(brief.anomaly_detected)

    def test_brief_caution_when_volatile_regime(self):
        analyst = self.ResearchAnalyst()
        brief = analyst.build_brief(self._composite(regime="BULL_VOLATILE"))
        self.assertEqual(brief.alert_level, "CAUTION")

    def test_brief_caution_high_volatility(self):
        analyst = self.ResearchAnalyst()
        brief = analyst.build_brief(self._composite(volatility=60.0))
        self.assertEqual(brief.alert_level, "CAUTION")

    def test_brief_danger_severe_anomaly(self):
        analyst = self.ResearchAnalyst()
        analyst.record_anomaly({
            "symbol": "AAPL", "exchange": "US",
            "anomaly_type": "PRICE_DROP", "severity": 0.85,
        })
        brief = analyst.build_brief(self._composite())
        self.assertEqual(brief.alert_level, "DANGER")
        self.assertTrue(brief.anomaly_detected)
        self.assertEqual(brief.anomaly_type, "PRICE_DROP")

    def test_brief_caution_mild_anomaly(self):
        analyst = self.ResearchAnalyst()
        analyst.record_anomaly({
            "symbol": "AAPL", "exchange": "US",
            "anomaly_type": "VOLUME_SPIKE", "severity": 0.40,
        })
        brief = analyst.build_brief(self._composite())
        self.assertEqual(brief.alert_level, "CAUTION")

    def test_anomaly_consumed_after_brief(self):
        analyst = self.ResearchAnalyst()
        analyst.record_anomaly({
            "symbol": "AAPL", "exchange": "US",
            "anomaly_type": "VOLUME_SPIKE", "severity": 0.9,
        })
        brief1 = analyst.build_brief(self._composite())
        self.assertTrue(brief1.anomaly_detected)
        # Second brief — anomaly already consumed
        brief2 = analyst.build_brief(self._composite())
        self.assertFalse(brief2.anomaly_detected)

    def test_bearish_sentiment_sell_signal(self):
        analyst = self.ResearchAnalyst()
        brief = analyst.build_brief(self._composite(signal="SELL", causal_effect=-0.2))
        self.assertEqual(brief.market_sentiment, "BEARISH")

    def test_neutral_hold_signal(self):
        analyst = self.ResearchAnalyst()
        brief = analyst.build_brief(self._composite(signal="HOLD", causal_effect=0.0))
        self.assertEqual(brief.market_sentiment, "NEUTRAL")

    def test_to_dict_has_all_fields(self):
        analyst = self.ResearchAnalyst()
        brief = analyst.build_brief(self._composite())
        d = brief.to_dict()
        for key in (
            "symbol", "exchange", "signal", "alert_level", "market_sentiment",
            "anomaly_detected", "anomaly_severity", "regime", "volatility",
        ):
            self.assertIn(key, d, f"Missing field: {key}")

    def test_anomaly_exchange_keyed(self):
        analyst = self.ResearchAnalyst()
        analyst.record_anomaly({
            "symbol": "BTCUSDT", "exchange": "BINANCE",
            "anomaly_type": "PRICE_GAP_UP", "severity": 0.8,
        })
        # Different exchange — no match
        brief_us = analyst.build_brief(self._composite(symbol="BTCUSDT", exchange="US"))
        self.assertFalse(brief_us.anomaly_detected)
        # Still available for BINANCE
        brief_binance = analyst.build_brief(self._composite(symbol="BTCUSDT", exchange="BINANCE"))
        self.assertTrue(brief_binance.anomaly_detected)


# ═════════════════════════════════════════════════════════════════════════════
# RiskGuardian tests
# ═════════════════════════════════════════════════════════════════════════════

class TestRiskGuardian(unittest.TestCase):

    def setUp(self):
        self.guardian = RiskGuardian()
        self.risk_mgr = RiskManager()
        self.tracker  = PositionTracker()
        self.config   = _make_config()

    def _evaluate(self, signal):
        return self.guardian.evaluate(
            signal, self.config, self.risk_mgr, self.tracker, "user1"
        )

    # ── Non-BUY signals are never vetoed ──────────────────────────────────

    def test_sell_not_vetoed(self):
        result = self._evaluate({**_buy_signal(), "signal": "SELL"})
        self.assertFalse(result.vetoed)

    def test_hold_not_vetoed(self):
        result = self._evaluate({**_buy_signal(), "signal": "HOLD"})
        self.assertFalse(result.vetoed)

    # ── DANGER alert → hard veto ──────────────────────────────────────────

    def test_danger_alert_blocks_buy(self):
        result = self._evaluate(_buy_signal(alert_level="DANGER"))
        self.assertTrue(result.vetoed)
        self.assertEqual(result.severity, "HARD")

    def test_caution_does_not_veto(self):
        result = self._evaluate(_buy_signal(alert_level="CAUTION"))
        self.assertFalse(result.vetoed)

    def test_normal_passes(self):
        result = self._evaluate(_buy_signal())
        self.assertFalse(result.vetoed)

    # ── Volatile regime position cap ──────────────────────────────────────

    def test_volatile_regime_cap_enforced(self):
        # Open 2 positions (the cap)
        self.tracker.record_open("user1", "AAPL", 1.0, 100.0)
        self.tracker.record_open("user1", "MSFT", 1.0, 200.0)
        result = self._evaluate(_buy_signal(regime="BULL_VOLATILE"))
        self.assertTrue(result.vetoed)
        self.assertEqual(result.severity, "SOFT")

    def test_volatile_regime_under_cap_passes(self):
        # 1 position open → under volatile cap of 2; small position size avoids concentration check
        self.tracker.record_open("user1", "AAPL", 1.0, 100.0)
        small_cfg = _make_config(max_position_size_usd=10)  # 10*0.75=7.5 → 7% of portfolio
        result = self.guardian.evaluate(
            _buy_signal(regime="BEAR_VOLATILE"), small_cfg,
            self.risk_mgr, self.tracker, "user1"
        )
        self.assertFalse(result.vetoed)

    def test_non_volatile_regime_ignores_cap(self):
        # 3 positions open; non-volatile → volatile cap doesn't apply; small pos avoids concentration
        self.tracker.record_open("user1", "AAPL", 1.0, 100.0)
        self.tracker.record_open("user1", "MSFT", 1.0, 200.0)
        self.tracker.record_open("user1", "GOOG", 1.0, 150.0)
        small_cfg = _make_config(max_position_size_usd=10)  # 10*0.75=7.5 → 1.6% of portfolio
        result = self.guardian.evaluate(
            _buy_signal(regime="BULL_QUIET"), small_cfg,
            self.risk_mgr, self.tracker, "user1"
        )
        self.assertFalse(result.vetoed)  # Guardian doesn't apply volatile cap in non-volatile regime

    # ── Daily decision cap ────────────────────────────────────────────────

    def test_daily_cap_hard_veto(self):
        state = self.risk_mgr._get_state("user1")
        state.decisions_today = RiskGuardian.MAX_DECISIONS_PER_DAY
        result = self._evaluate(_buy_signal())
        self.assertTrue(result.vetoed)
        self.assertEqual(result.severity, "HARD")

    def test_under_cap_passes(self):
        state = self.risk_mgr._get_state("user1")
        state.decisions_today = RiskGuardian.MAX_DECISIONS_PER_DAY - 1
        result = self._evaluate(_buy_signal())
        self.assertFalse(result.vetoed)

    # ── Portfolio concentration ───────────────────────────────────────────

    def test_concentration_limit_soft_veto(self):
        # Portfolio value = 100; proposed = 500 * 0.75 = 375 → 79% concentration
        self.tracker.record_open("user1", "AAPL", 1.0, 100.0)
        result = self._evaluate(_buy_signal(price=100.0))
        self.assertTrue(result.vetoed)
        self.assertEqual(result.severity, "SOFT")

    def test_empty_portfolio_no_concentration_veto(self):
        # No existing positions → portfolio_value = 0 → skip concentration check
        result = self._evaluate(_buy_signal())
        self.assertFalse(result.vetoed)


# ═════════════════════════════════════════════════════════════════════════════
# ExecutionSpecialist tests
# ═════════════════════════════════════════════════════════════════════════════

class TestExecutionSpecialist(unittest.TestCase):

    def setUp(self):
        self.specialist = ExecutionSpecialist()
        self.tracker    = PositionTracker()
        self.risk_mgr   = RiskManager()
        self.scorer     = MagicMock()
        self.scorer.record_open  = AsyncMock()
        self.scorer.record_close = AsyncMock()

    def _claude_rec(self, recommendation="APPROVE", confidence=0.8, pnl=5.0):
        rec = MagicMock()
        rec.recommendation = recommendation
        rec.confidence     = confidence
        rec.reasoning      = "Test reasoning"
        rec.expected_pnl   = pnl
        return rec

    def _broker(self, broker_id="ORDER123"):
        client = MagicMock()
        order_resp = MagicMock()
        order_resp.broker_id = broker_id
        client.place_order    = AsyncMock(return_value=order_resp)
        client.close_position = AsyncMock(return_value=order_resp)
        return client

    def test_open_long_executed(self):
        client = self._broker()
        result = asyncio.get_event_loop().run_until_complete(
            self.specialist.open_long(
                user_id="u1", symbol="AAPL", quantity=5.0,
                signal_data={"signal": "BUY", "current_price": 100.0},
                claude_rec=self._claude_rec(),
                client=client, pool=None, conn_id=None,
                tracker=self.tracker, scorer=self.scorer,
                claude_decision_id=None,
            )
        )
        self.assertEqual(result.status, "EXECUTED")
        self.assertEqual(result.broker_order_id, "ORDER123")
        pos = self.tracker.get_position("u1", "AAPL")
        self.assertIsNotNone(pos)
        self.assertAlmostEqual(pos.quantity, 5.0)

    def test_open_long_failed(self):
        client = MagicMock()
        client.place_order = AsyncMock(side_effect=Exception("Broker error"))
        result = asyncio.get_event_loop().run_until_complete(
            self.specialist.open_long(
                user_id="u1", symbol="AAPL", quantity=5.0,
                signal_data={"signal": "BUY", "current_price": 100.0},
                claude_rec=self._claude_rec(),
                client=client, pool=None, conn_id=None,
                tracker=self.tracker, scorer=self.scorer,
                claude_decision_id=None,
            )
        )
        self.assertEqual(result.status, "FAILED")

    def test_close_long_executed_and_pnl(self):
        # Set up an existing position at entry $100
        self.tracker.record_open("u1", "AAPL", 5.0, 100.0)
        client = self._broker()
        result = asyncio.get_event_loop().run_until_complete(
            self.specialist.close_long(
                user_id="u1", symbol="AAPL", quantity=5.0,
                signal_data={"signal": "SELL", "current_price": 110.0},
                claude_rec=self._claude_rec(),
                client=client, pool=None, conn_id=None,
                tracker=self.tracker, risk_mgr=self.risk_mgr,
                scorer=self.scorer,
            )
        )
        self.assertEqual(result.status, "EXECUTED")
        self.assertAlmostEqual(result.pnl, 50.0)  # (110 - 100) * 5

    def test_close_long_records_pnl_in_risk_mgr(self):
        self.tracker.record_open("u1", "AAPL", 10.0, 100.0)
        client = self._broker()
        asyncio.get_event_loop().run_until_complete(
            self.specialist.close_long(
                user_id="u1", symbol="AAPL", quantity=10.0,
                signal_data={"signal": "SELL", "current_price": 105.0},
                claude_rec=self._claude_rec(),
                client=client, pool=None, conn_id=None,
                tracker=self.tracker, risk_mgr=self.risk_mgr,
                scorer=self.scorer,
            )
        )
        state = self.risk_mgr.get_state("u1")
        self.assertAlmostEqual(state.daily_realized_pnl, 50.0)  # (105-100)*10

    def test_close_removes_position(self):
        self.tracker.record_open("u1", "AAPL", 5.0, 100.0)
        client = self._broker()
        asyncio.get_event_loop().run_until_complete(
            self.specialist.close_long(
                user_id="u1", symbol="AAPL", quantity=5.0,
                signal_data={"signal": "SELL", "current_price": 100.0},
                claude_rec=self._claude_rec(),
                client=client, pool=None, conn_id=None,
                tracker=self.tracker, risk_mgr=self.risk_mgr,
                scorer=self.scorer,
            )
        )
        self.assertIsNone(self.tracker.get_position("u1", "AAPL"))


# ═════════════════════════════════════════════════════════════════════════════
# StrategyArchitect tests
# ═════════════════════════════════════════════════════════════════════════════

class TestStrategyArchitect(unittest.TestCase):

    def _make_architect(self):
        from src.strategy_architect import StrategyArchitect
        from src.decision_engine import DecisionEngine, Decision
        from src.claude_layer import ClaudeRecommendation

        from src.portfolio_optimizer import PortfolioOptimizer

        engine    = DecisionEngine()
        tracker   = PositionTracker()
        risk_mgr  = RiskManager()
        guardian  = RiskGuardian()
        optimizer = PortfolioOptimizer()
        scorer    = MagicMock()
        scorer.get_symbol_score = MagicMock(return_value=None)

        claude = MagicMock()
        approve_rec = ClaudeRecommendation(
            execute=True, confidence=0.85,
            reasoning="Looks good.", recommendation="APPROVE",
        )
        claude.evaluate = AsyncMock(return_value=approve_rec)

        architect = StrategyArchitect(
            engine=engine, claude=claude, guardian=guardian,
            risk_mgr=risk_mgr, tracker=tracker, scorer=scorer,
            optimizer=optimizer,
        )
        return architect, tracker, risk_mgr, Decision

    def _account(self, equity=10000.0, buying_power=5000.0):
        acc = MagicMock(spec=AccountInfo)
        acc.equity       = equity
        acc.buying_power = buying_power
        acc.cash         = equity
        return acc

    def test_guardian_veto_returns_hold(self):
        from src.strategy_architect import StrategyArchitect
        architect, tracker, risk_mgr, Decision = self._make_architect()
        signal = _buy_signal(alert_level="DANGER")
        result = asyncio.get_event_loop().run_until_complete(
            architect.evaluate(
                user_id="u1", config=_make_config(),
                signal_data=signal, account=self._account(),
                pool=None, http_client=None, questdb_url="",
                risk_profile=None,
            )
        )
        self.assertEqual(result.decision.action, "HOLD")
        self.assertTrue(result.guardian_result.vetoed)
        self.assertEqual(result.guardian_result.severity, "HARD")
        # Claude should NOT have been called
        architect._claude.evaluate.assert_not_called()

    def test_claude_approve_opens_long(self):
        architect, tracker, risk_mgr, _ = self._make_architect()
        signal = _buy_signal()
        with patch("src.strategy_architect.load_position_risks", new=AsyncMock(return_value=[])), \
             patch("src.strategy_architect.load_recent_signal_history", new=AsyncMock(return_value=[])), \
             patch("src.strategy_architect.save_claude_decision", new=AsyncMock(return_value="dec1")):
            result = asyncio.get_event_loop().run_until_complete(
                architect.evaluate(
                    user_id="u1", config=_make_config(),
                    signal_data=signal, account=self._account(),
                    pool=MagicMock(), http_client=MagicMock(),
                    questdb_url="http://questdb:9010",
                    risk_profile=None,
                )
            )
        self.assertEqual(result.decision.action, "OPEN_LONG")
        self.assertFalse(result.guardian_result.vetoed)

    def test_claude_reject_converts_to_hold(self):
        from src.claude_layer import ClaudeRecommendation
        architect, tracker, risk_mgr, _ = self._make_architect()
        reject_rec = ClaudeRecommendation(
            execute=False, confidence=0.3,
            reasoning="Bad signal.", recommendation="REJECT",
        )
        architect._claude.evaluate = AsyncMock(return_value=reject_rec)
        signal = _buy_signal()
        with patch("src.strategy_architect.load_position_risks", new=AsyncMock(return_value=[])), \
             patch("src.strategy_architect.load_recent_signal_history", new=AsyncMock(return_value=[])), \
             patch("src.strategy_architect.save_claude_decision", new=AsyncMock(return_value="dec1")):
            result = asyncio.get_event_loop().run_until_complete(
                architect.evaluate(
                    user_id="u1", config=_make_config(),
                    signal_data=signal, account=self._account(),
                    pool=MagicMock(), http_client=MagicMock(),
                    questdb_url="http://questdb:9010",
                    risk_profile=None,
                )
            )
        self.assertEqual(result.decision.action, "HOLD")
        self.assertIn("Claude rejected", result.decision.reason)

    def test_claude_reduce_shrinks_quantity(self):
        from src.claude_layer import ClaudeRecommendation
        architect, tracker, risk_mgr, _ = self._make_architect()
        reduce_rec = ClaudeRecommendation(
            execute=True, confidence=0.7,
            reasoning="High vol — reduce.", recommendation="REDUCE",
            adjusted_size=0.5,
        )
        architect._claude.evaluate = AsyncMock(return_value=reduce_rec)
        signal = _buy_signal()
        with patch("src.strategy_architect.load_position_risks", new=AsyncMock(return_value=[])), \
             patch("src.strategy_architect.load_recent_signal_history", new=AsyncMock(return_value=[])), \
             patch("src.strategy_architect.save_claude_decision", new=AsyncMock(return_value="dec1")):
            result = asyncio.get_event_loop().run_until_complete(
                architect.evaluate(
                    user_id="u1", config=_make_config(),
                    signal_data=signal, account=self._account(buying_power=50000.0),
                    pool=MagicMock(), http_client=MagicMock(),
                    questdb_url="http://questdb:9010",
                    risk_profile=None,
                )
            )
        self.assertEqual(result.decision.action, "OPEN_LONG")
        # quantity should be halved
        self.assertGreater(result.decision.quantity, 0)


if __name__ == "__main__":
    unittest.main()
