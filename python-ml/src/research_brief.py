"""
Research Analyst — builds structured Research Briefs from ML signals + anomaly alerts.

The ResearchAnalyst:
  1. Receives MarketAnomaly events from the Rust Market Sentinel
  2. Merges them with the composite ML signal for each symbol
  3. Derives alert_level and market_sentiment
  4. Publishes ml.research.brief on NATS (in addition to ml.signals.composite)
"""

from dataclasses import dataclass
from datetime import datetime, timezone

import structlog

logger = structlog.get_logger()


@dataclass
class ResearchBrief:
    # Identity
    symbol: str
    exchange: str
    timestamp: str
    # Signal
    signal: str
    ensemble_confidence: float
    expected_return: float
    predicted_close: float
    # Regime
    regime: str
    volatility: float
    causal_effect: float
    causal_n_significant: int
    # Anomaly
    anomaly_detected: bool
    anomaly_type: str | None
    anomaly_severity: float
    # Derived
    alert_level: str    # "NORMAL" | "CAUTION" | "DANGER"
    market_sentiment: str  # "BULLISH" | "NEUTRAL" | "BEARISH"

    def to_dict(self) -> dict:
        return {
            "symbol":               self.symbol,
            "exchange":             self.exchange,
            "timestamp":            self.timestamp,
            "signal":               self.signal,
            "ensemble_confidence":  self.ensemble_confidence,
            "expected_return":      self.expected_return,
            "predicted_close":      self.predicted_close,
            "regime":               self.regime,
            "volatility":           self.volatility,
            "causal_effect":        self.causal_effect,
            "causal_n_significant": self.causal_n_significant,
            "anomaly_detected":     self.anomaly_detected,
            "anomaly_type":         self.anomaly_type,
            "anomaly_severity":     self.anomaly_severity,
            "alert_level":          self.alert_level,
            "market_sentiment":     self.market_sentiment,
        }


class ResearchAnalyst:
    """
    Aggregates ML composite signals + Rust anomaly alerts into Research Briefs.

    Anomalies are consumed once per build — they don't repeat across multiple
    snapshots for the same symbol unless a new anomaly arrives.
    """

    def __init__(self):
        # Latest anomaly per "EXCHANGE:SYMBOL" key (consumed on next brief build)
        self._anomalies: dict[str, dict] = {}

    def record_anomaly(self, anomaly: dict) -> None:
        """Called when a market.anomaly.* NATS message arrives from Rust."""
        key = f"{anomaly.get('exchange', 'US')}:{anomaly['symbol']}"
        self._anomalies[key] = anomaly
        logger.info(
            "Anomaly recorded",
            symbol=anomaly["symbol"],
            type=anomaly.get("anomaly_type"),
            severity=round(anomaly.get("severity", 0.0), 3),
        )

    def build_brief(self, composite: dict) -> ResearchBrief:
        """Build a ResearchBrief from an ml.signals.composite message."""
        symbol   = composite["symbol"]
        exchange = composite.get("exchange", "US")
        key      = f"{exchange}:{symbol}"

        # Consume anomaly for this symbol (pop so it doesn't repeat next cycle)
        anomaly         = self._anomalies.pop(key, None)
        anomaly_detected = anomaly is not None
        anomaly_type     = anomaly.get("anomaly_type") if anomaly else None
        anomaly_severity = float(anomaly.get("severity", 0.0)) if anomaly else 0.0

        # ── Alert level ──────────────────────────────────────────────────────
        regime     = composite.get("regime", "SIDEWAYS")
        volatility = composite.get("volatility", 0.0) or 0.0
        is_volatile = "VOLATILE" in regime or volatility > 50.0

        if anomaly_detected and anomaly_severity > 0.6:
            alert_level = "DANGER"
        elif anomaly_detected or is_volatile:
            alert_level = "CAUTION"
        else:
            alert_level = "NORMAL"

        # ── Market sentiment ─────────────────────────────────────────────────
        signal       = composite.get("signal", "HOLD")
        causal_effect = composite.get("causal_effect", 0.0) or 0.0

        if signal == "BUY" and causal_effect > 0:
            market_sentiment = "BULLISH"
        elif signal == "SELL" or causal_effect < -0.1:
            market_sentiment = "BEARISH"
        else:
            market_sentiment = "NEUTRAL"

        return ResearchBrief(
            symbol               = symbol,
            exchange             = exchange,
            timestamp            = composite.get(
                "timestamp", datetime.now(timezone.utc).isoformat()
            ),
            signal               = signal,
            ensemble_confidence  = float(composite.get("ensemble_confidence", 0.0) or 0.0),
            expected_return      = float(composite.get("ensemble_expected_return", 0.0) or 0.0),
            predicted_close      = float(composite.get("predicted_close", 0.0) or 0.0),
            regime               = regime,
            volatility           = volatility,
            causal_effect        = causal_effect,
            causal_n_significant = int(composite.get("causal_n_significant", 0) or 0),
            anomaly_detected     = anomaly_detected,
            anomaly_type         = anomaly_type,
            anomaly_severity     = anomaly_severity,
            alert_level          = alert_level,
            market_sentiment     = market_sentiment,
        )
