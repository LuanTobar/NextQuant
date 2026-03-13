import asyncio
import json
import logging
import signal
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
import structlog
import httpx

from src.config import settings


def _configure_logging() -> None:
    """Wire structlog to respect settings.log_level (reads LOG_LEVEL env var)."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
from src.nats_client import NATSClient
from src.models.causal_analyzer import CausalAnalyzer
from src.models.predictive_model import PredictiveModel
from src.models.regime_classifier import RegimeClassifier
from src.models.ensemble import EnsemblePredictor
from src.models.model_store import ModelStore
from src.features import FeatureStore
from src.research_brief import ResearchAnalyst

logger = structlog.get_logger()

# Global liveness timestamp — updated on each tick
_last_tick_ts: float = time.time()
# Global model status — updated every checkpoint (10 min)
_model_status: dict = {}


def _start_health_server(port: int) -> None:
    """Lightweight HTTP server for Docker healthcheck on a background thread."""
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                age = time.time() - _last_tick_ts
                # Healthy if we processed a tick in the last 120s (or just started)
                healthy = age < 120
                body = json.dumps({
                    "status": "ok" if healthy else "degraded",
                    "last_tick_age_s": round(age, 1),
                    "model_status": _model_status,
                }).encode()
                self.send_response(200 if healthy else 503)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *args):
            pass  # suppress access logs

    server = HTTPServer(("0.0.0.0", port), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    logger.info("Health server started", port=port)


class MLService:
    def __init__(self):
        self.nats = NATSClient(settings.nats_url)
        # Sprint 1.3: upgraded Granger + TE causal engine (lookback=100, analyze every 50 ticks)
        self.causal = CausalAnalyzer(lookback=100, analyze_every=50)
        self.predictor = PredictiveModel(window=20)
        self.regime = RegimeClassifier(window=20)
        self.feature_store = FeatureStore(cache_ttl_s=5.0)
        # Sprint 1.2: Ensemble predictor (LGBM + LSTM + GARCH stacking)
        self.ensemble = EnsemblePredictor(
            lgbm_kwargs={"retrain_every": 500, "horizon_bars": 60},
            lstm_kwargs={"retrain_every": 500, "horizon_bars": 12},
            meta_retrain_every=200,
            horizon_bars=60,
        )
        self.analyst = ResearchAnalyst()
        self.tick_count = 0
        self.http_client = httpx.AsyncClient(timeout=10.0)
        self.questdb_url = settings.questdb_url
        # Sprint 2.4: Model lifecycle — persistence + drift + versioning
        self.store = ModelStore(settings.model_save_path)

    async def start(self):
        logger.info("Starting NexQuant ML Service")
        _start_health_server(settings.health_port)

        # Sprint 2.4: Load persisted models before anything else
        await asyncio.get_event_loop().run_in_executor(None, self._load_persisted_models)

        # Pre-warm FeatureStore (triggers pandas_ta lazy imports once at startup)
        await asyncio.get_event_loop().run_in_executor(None, self._prewarm_features)

        # Ensure QuestDB schema exists
        await self._ensure_schema()

        # Retry NATS connection
        for attempt in range(1, 11):
            try:
                await self.nats.connect()
                break
            except Exception as e:
                logger.warning("NATS not ready", attempt=attempt, error=str(e))
                await asyncio.sleep(2)
        else:
            raise RuntimeError("Failed to connect to NATS after 10 attempts")

        await self.nats.subscribe("market.snapshot", self.on_snapshot)
        # Subscribe to multi-market tick subjects: market.tick.{EXCHANGE}.{SYMBOL}
        await self.nats.subscribe("market.tick.>", self.on_tick)
        # Subscribe to Rust Market Sentinel anomalies: market.anomaly.{EXCHANGE}.{SYMBOL}
        await self.nats.subscribe("market.anomaly.>", self.on_anomaly)

        # Sprint 2.4: periodic model checkpoint every 10 minutes
        asyncio.create_task(self._checkpoint_loop())

        logger.info("ML Service running, waiting for market data...")

        # Keep alive
        stop = asyncio.Event()
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop.set)
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                pass

        try:
            await stop.wait()
        except asyncio.CancelledError:
            pass
        finally:
            await self.http_client.aclose()
            await self.nats.close()

    async def on_anomaly(self, msg):
        """Receive Market Sentinel anomaly from Rust and store in ResearchAnalyst."""
        try:
            anomaly = json.loads(msg.data)
            self.analyst.record_anomaly(anomaly)
        except Exception as e:
            logger.warning("Error processing anomaly", error=str(e))

    async def on_tick(self, msg):
        """Process individual ticks - feed to models."""
        global _last_tick_ts
        try:
            tick = json.loads(msg.data)
            symbol = tick["symbol"]
            exchange = tick.get("exchange", "US")
            close = tick["close"]

            # Use exchange:symbol as key for multi-market support
            key = f"{exchange}:{symbol}"
            self.causal.add_tick(tick)
            self.predictor.add_tick(key, close)
            self.regime.add_tick(key, close)
            self.feature_store.add_tick(tick)
            self.tick_count += 1
            _last_tick_ts = time.time()
        except Exception as e:
            logger.error("Error processing tick", error=str(e))

    async def on_snapshot(self, msg):
        """Process snapshots - run full analysis and publish signals."""
        try:
            snapshot = json.loads(msg.data)
            ticks = snapshot.get("ticks", [])

            for tick in ticks:
                symbol = tick["symbol"]
                exchange = tick.get("exchange", "US")
                key = f"{exchange}:{symbol}"

                # Run legacy models + Sprint 1.3 causal engine
                causal_result = self.causal.analyze(symbol, exchange)
                prediction = self.predictor.predict(key)
                regime_result = self.regime.classify(key)

                # Compute FeatureStore features (non-blocking, cached)
                features = self.feature_store.compute_features(exchange, symbol)
                feature_count = sum(1 for k in features if not k.startswith("_"))

                # Sprint 1.2: Ensemble observe + predict
                current_price = float(tick["close"])
                if features:
                    self.ensemble.observe(current_price, features)
                ensemble_result = self.ensemble.predict(features or {})

                # Primary signal: ensemble when trained, legacy fallback otherwise
                if ensemble_result["is_trained"]:
                    signal_value    = ensemble_result["signal"]
                    expected_ret    = ensemble_result["expected_return"]
                    predicted_close = round(current_price * (1.0 + expected_ret), 4)
                    confidence_low  = round(current_price * (1.0 + ensemble_result["ci_low"]), 4)
                    confidence_high = round(current_price * (1.0 + ensemble_result["ci_high"]), 4)
                else:
                    signal_value    = self._generate_signal(causal_result, prediction, regime_result, tick)
                    predicted_close = prediction["predicted_close"]
                    confidence_low  = prediction["confidence_low"]
                    confidence_high = prediction["confidence_high"]

                # Build composite — features + ensemble enrichment for all downstream agents
                composite = {
                    "timestamp": snapshot["timestamp"],
                    "symbol": symbol,
                    "exchange": exchange,
                    "current_price": current_price,
                    "signal": signal_value,
                    "causal_effect": causal_result["causal_effect"],
                    "causal_method": causal_result["method"],
                    "causal_description": causal_result["description"],
                    "predicted_close": predicted_close,
                    "confidence_low": confidence_low,
                    "confidence_high": confidence_high,
                    "regime": regime_result["regime"],
                    "regime_probabilities": regime_result["probabilities"],
                    "volatility": features.get("ms_realized_vol_60b", regime_result["volatility"]),
                    # FeatureStore enrichment
                    "feature_count": feature_count,
                    "rsi_14": features.get("tf_raw_rsi_14"),
                    "rsi_28": features.get("tf_raw_rsi_28"),
                    "macd_hist": features.get("tf_raw_macd_hist"),
                    "bb_pct_b": features.get("tf_raw_bb_pct_b"),
                    "volume_imbalance": features.get("ms_volume_imbalance"),
                    "vwap_deviation": features.get("ms_vwap_deviation"),
                    "momentum_5b": features.get("mom_return_5b"),
                    "momentum_20b": features.get("mom_return_20b"),
                    "trend_r2": features.get("mom_trend_r2"),
                    # Ensemble enrichment (Sprint 1.2)
                    "ensemble_signal": ensemble_result["signal"],
                    "ensemble_confidence": ensemble_result["confidence"],
                    "ensemble_method": ensemble_result["method"],
                    "ensemble_expected_return": ensemble_result["expected_return"],
                    "ensemble_is_trained": ensemble_result["is_trained"],
                    "lgbm_prob": ensemble_result.get("lgbm_prob"),
                    "lstm_confidence_score": ensemble_result.get("lstm_confidence"),
                    "vol_regime_prob": ensemble_result.get("vol_regime_prob"),
                    # Causal alpha pipeline (Sprint 1.3)
                    "causal_n_significant": causal_result.get("n_significant", 0),
                    "causal_alpha_signal": causal_result.get("alpha_signal", 0.0),
                    "causal_relationships": causal_result.get("relationships", []),
                    # HMM regime enrichment (Sprint 1.3)
                    "regime_state_idx": regime_result.get("state_idx", -1),
                    "regime_method": regime_result.get("method", "volatility_threshold"),
                }

                # Build Research Brief (merges anomaly + sentiment) and enrich composite
                brief = self.analyst.build_brief(composite)
                composite["alert_level"]      = brief.alert_level
                composite["market_sentiment"] = brief.market_sentiment
                composite["anomaly_detected"] = brief.anomaly_detected
                composite["anomaly_type"]     = brief.anomaly_type
                composite["anomaly_severity"] = brief.anomaly_severity

                await self.nats.publish("ml.signals.composite", composite)
                await self.nats.publish("ml.research.brief", brief.to_dict())

                # Persist signal and features to QuestDB
                await self._persist_signal(composite)
                if feature_count > 0:
                    await self._persist_features(exchange, symbol, snapshot["timestamp"], features)

            logger.info(
                "Published signals",
                symbols=len(ticks),
                total_ticks=self.tick_count,
            )
        except Exception as e:
            logger.error("Error processing snapshot", error=str(e))

    async def _ensure_schema(self):
        """Create QuestDB tables if they don't exist."""
        queries = [
            (
                "CREATE TABLE IF NOT EXISTS ml_signals ("
                "timestamp TIMESTAMP, symbol SYMBOL, exchange SYMBOL, "
                "signal STRING, current_price DOUBLE, predicted_close DOUBLE, "
                "confidence_low DOUBLE, confidence_high DOUBLE, regime STRING, "
                "causal_effect DOUBLE, causal_description STRING, volatility DOUBLE"
                ") TIMESTAMP(timestamp) PARTITION BY DAY;"
            ),
            (
                "CREATE TABLE IF NOT EXISTS feature_store ("
                "timestamp TIMESTAMP, symbol SYMBOL, exchange SYMBOL, "
                "feature_count INT, features STRING"
                ") TIMESTAMP(timestamp) PARTITION BY DAY;"
            ),
            (
                "CREATE TABLE IF NOT EXISTS causal_graph ("
                "timestamp TIMESTAMP, symbol SYMBOL, exchange SYMBOL, "
                "n_significant INT, alpha_signal DOUBLE, "
                "method STRING, relationships STRING"
                ") TIMESTAMP(timestamp) PARTITION BY DAY;"
            ),
        ]
        for query in queries:
            for attempt in range(1, 11):
                try:
                    url = f"{self.questdb_url}/exec"
                    resp = await self.http_client.get(url, params={"query": query})
                    if resp.status_code == 200:
                        break
                    logger.warning("QuestDB schema failed", status=resp.status_code, body=resp.text[:100])
                except Exception as e:
                    logger.warning("QuestDB not ready", attempt=attempt, error=str(e))
                await asyncio.sleep(2)
        logger.info("QuestDB schema ready")

    async def _persist_features(self, exchange: str, symbol: str, timestamp: str, features: dict):
        """Persist feature snapshot to QuestDB feature_store table (best-effort)."""
        try:
            import json as _json
            # Serialize only numeric features to avoid huge payloads
            numeric_features = {k: v for k, v in features.items() if isinstance(v, float) and not k.startswith("_")}
            features_json = _json.dumps(numeric_features).replace("'", "''")
            feature_count = len(numeric_features)
            query = (
                f"INSERT INTO feature_store (timestamp, symbol, exchange, feature_count, features) "
                f"VALUES ('{timestamp}', '{symbol}', '{exchange}', {feature_count}, '{features_json}');"
            )
            url = f"{self.questdb_url}/exec"
            await self.http_client.get(url, params={"query": query})
        except Exception as e:
            logger.debug("Feature persistence skipped", error=str(e))

    async def _persist_signal(self, composite: dict):
        """Insert a single ML signal into QuestDB."""
        try:
            # Escape single quotes in causal_description
            desc = composite.get("causal_description", "").replace("'", "''")
            exchange = composite.get("exchange", "US")
            query = (
                f"INSERT INTO ml_signals "
                f"(timestamp, symbol, exchange, signal, current_price, predicted_close, "
                f"confidence_low, confidence_high, regime, causal_effect, "
                f"causal_description, volatility) VALUES ("
                f"'{composite['timestamp']}', "
                f"'{composite['symbol']}', "
                f"'{exchange}', "
                f"'{composite['signal']}', "
                f"{composite['current_price']}, "
                f"{composite['predicted_close']}, "
                f"{composite['confidence_low']}, "
                f"{composite['confidence_high']}, "
                f"'{composite['regime']}', "
                f"{composite['causal_effect']}, "
                f"'{desc}', "
                f"{composite['volatility']});"
            )
            url = f"{self.questdb_url}/exec"
            resp = await self.http_client.get(url, params={"query": query})
            if resp.status_code != 200:
                logger.warning(
                    "Failed to persist signal",
                    symbol=composite["symbol"],
                    status=resp.status_code,
                )
        except Exception as e:
            logger.warning("Error persisting signal to QuestDB", error=str(e))

    def _load_persisted_models(self) -> None:
        """Load ensemble + regime from disk if available. Best-effort — never blocks startup."""
        state = self.store.load("ensemble")
        if state:
            try:
                self.ensemble.load_state(state)
                logger.info(
                    "Ensemble loaded from disk",
                    lgbm_trained=self.ensemble.lgbm.is_trained,
                    meta_trained=self.ensemble._meta_is_trained,
                )
            except Exception as e:
                logger.warning("Failed to restore ensemble state", error=str(e))

        state = self.store.load("regime")
        if state:
            try:
                self.regime.load_state(state)
                logger.info(
                    "Regime classifier loaded from disk",
                    n_symbols=len(self.regime._models),
                )
            except Exception as e:
                logger.warning("Failed to restore regime state", error=str(e))

    async def _checkpoint_loop(self) -> None:
        """Save models to disk every 10 minutes and run drift detection."""
        while True:
            await asyncio.sleep(600)  # 10 minutes
            await asyncio.get_event_loop().run_in_executor(None, self._checkpoint)

    def _checkpoint(self) -> None:
        """Persist ensemble + regime, detect LGBM drift, update health status."""
        global _model_status
        try:
            self.store.save("ensemble", self.ensemble.save_state())
            self.store.save("regime", self.regime.save_state())

            # Drift detection on LGBM rolling accuracy
            acc = self.ensemble.lgbm.rolling_accuracy(n=100)
            n_labeled = self.ensemble.lgbm.labeled_count
            self.store.record_version("ensemble", n_labeled, acc)

            if acc is not None and acc < 0.48:
                logger.warning(
                    "LGBM drift detected — accuracy below threshold",
                    rolling_accuracy=round(acc, 4),
                    threshold=0.48,
                )

            _model_status = self.store.get_model_status()
            logger.info("Model checkpoint saved", n_labeled=n_labeled, accuracy=acc)
        except Exception as e:
            logger.warning("Checkpoint failed", error=str(e))

    def _prewarm_features(self) -> None:
        """
        Pre-warm the FeatureStore by triggering pandas_ta lazy imports once.
        Runs in a thread executor during startup so it doesn't block the event loop.
        """
        import numpy as np
        import pandas as pd
        from src.features.technical import compute_technical_features

        rng = np.random.default_rng(0)
        prices = 100.0 + np.cumsum(rng.normal(0, 0.5, 50))
        df = pd.DataFrame({
            "open": prices * 0.999, "high": prices * 1.002,
            "low": prices * 0.998, "close": prices,
            "volume": np.ones(50) * 10000.0,
        })
        compute_technical_features(df)
        logger.info("FeatureStore pre-warmed")

    def _generate_signal(
        self, causal: dict, prediction: dict, regime: dict, tick: dict
    ) -> str:
        """Simple signal logic combining all three models."""
        current_price = tick["close"]
        predicted = prediction["predicted_close"]
        vol_regime = regime["regime"]

        # Price direction
        expected_return = (predicted - current_price) / current_price if current_price > 0 else 0

        # Threshold must exceed roundtrip fees (~0.2% crypto, ~0.1% stocks)
        # Handles both legacy 3-state ("HIGH_VOL") and Sprint 1.3 5-state regimes ("*_VOLATILE")
        threshold = 0.004 if ("VOLATILE" in vol_regime or vol_regime == "HIGH_VOL") else 0.002

        if expected_return > threshold:
            return "BUY"
        elif expected_return < -threshold:
            return "SELL"
        return "HOLD"


async def main():
    _configure_logging()
    service = MLService()
    await service.start()


if __name__ == "__main__":
    asyncio.run(main())
