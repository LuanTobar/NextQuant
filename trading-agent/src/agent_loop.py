"""
Core agent loop — subscribes to ML signals, dispatches per-user decisions.
"""

import asyncio
import json
import signal
import time
from datetime import datetime, timezone

import structlog

import httpx

from .config import Settings
from .claude_layer import ClaudeLayer
from .db import (
    AgentConfig,
    create_pool,
    get_risk_profile,
    load_all_agent_configs,
    load_broker_connection,
)
from .encryption import decrypt
from .nats_client import NATSClient
from .brokers import create_broker_client
from .brokers.base import BrokerClient
from .decision_engine import DecisionEngine
from .execution_specialist import ExecutionSpecialist
from .position_tracker import PositionTracker
from .risk_guardian import RiskGuardian
from .risk_manager import RiskManager
from .alerter import Alerter
from .portfolio_optimizer import PortfolioOptimizer
from .score_tracker import ScoreTracker
from .strategy_architect import StrategyArchitect

logger = structlog.get_logger()


class AgentLoop:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._nats = NATSClient(settings.nats_url)
        self._pool = None
        self._tracker    = PositionTracker()
        self._risk_mgr   = RiskManager()
        self._engine     = DecisionEngine()
        self._claude     = ClaudeLayer(settings)
        self._scorer     = ScoreTracker()
        self._guardian   = RiskGuardian()
        self._optimizer  = PortfolioOptimizer()
        self._alerter    = Alerter(settings.alert_webhook_url)
        self._http_client = httpx.AsyncClient(timeout=10.0)
        # Specialist agents (Sprint 1.6)
        self._architect = StrategyArchitect(
            engine=self._engine,
            claude=self._claude,
            guardian=self._guardian,
            risk_mgr=self._risk_mgr,
            tracker=self._tracker,
            scorer=self._scorer,
            optimizer=self._optimizer,
        )
        self._executor  = ExecutionSpecialist()
        self._configs: dict[str, AgentConfig] = {}       # user_id -> config
        self._clients: dict[str, BrokerClient] = {}      # user_id -> broker client
        self._conn_ids: dict[str, str] = {}               # user_id -> broker connection ID
        self._risk_profiles: dict[str, dict] = {}         # user_id -> {risk_score, risk_category}
        self._signal_locks: dict[str, asyncio.Lock] = {}  # "{user_id}:{symbol}" -> Lock
        self._bg_tasks: list[asyncio.Task] = []
        self._running = True
        self._start_time = time.time()

    async def start(self):
        logger.info("Starting trading agent")

        # Connect to PostgreSQL
        self._pool = await create_pool(self._settings.database_url)

        # Connect to NATS with retry (library handles runtime reconnection automatically)
        for attempt in range(3):
            try:
                await self._nats.connect()
                break
            except Exception as e:
                logger.warning("NATS connect failed, retrying", attempt=attempt, error=str(e))
                await asyncio.sleep(2)
        else:
            raise RuntimeError("Failed to connect to NATS after 3 attempts")

        # Ensure QuestDB claude_decisions table exists
        await self._ensure_questdb_schema()

        # Load configs and build broker clients
        await self._reload_configs()

        # Load historical scores for each user
        for user_id in self._configs:
            await self._scorer.load_scores(self._pool, user_id)

        # Subscribe to ML signals
        await self._nats.subscribe("ml.signals.composite", self._on_signal)

        # Subscribe to commands for each user
        for user_id in self._configs:
            await self._nats.subscribe(
                f"agent.command.{user_id}", self._on_command
            )

        # Start background tasks (tracked for graceful shutdown)
        self._bg_tasks = [
            asyncio.create_task(self._config_reload_loop()),
            asyncio.create_task(self._position_sync_loop()),
            asyncio.create_task(self._status_publish_loop()),
            asyncio.create_task(self._health_server()),
        ]

        logger.info(
            "Agent running",
            users=len(self._configs),
            config_reload_s=self._settings.config_reload_interval_s,
        )

        # Wait for shutdown
        stop = asyncio.Event()

        def _stop():
            self._running = False
            stop.set()

        try:
            loop = asyncio.get_running_loop()
            loop.add_signal_handler(signal.SIGINT, _stop)
            loop.add_signal_handler(signal.SIGTERM, _stop)
        except NotImplementedError:
            pass  # Windows

        await stop.wait()
        await self._shutdown()

    async def _shutdown(self):
        logger.info("Shutting down agent")
        for task in self._bg_tasks:
            task.cancel()
        await asyncio.gather(*self._bg_tasks, return_exceptions=True)
        try:
            await asyncio.wait_for(self._claude.close(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("Claude close timed out")
        await self._http_client.aclose()
        await self._nats.close()
        if self._pool:
            await self._pool.close()
        logger.info("Agent shutdown complete")

    # ── Signal handler ───────────────────────────────────────────

    async def _on_signal(self, msg):
        try:
            signal_data = json.loads(msg.data.decode())
        except Exception:
            return

        symbol = signal_data.get("symbol", "")
        if not symbol:
            return

        sig = signal_data.get("signal", "?")
        logger.debug("Signal received", symbol=symbol, signal=sig)

        for user_id, config in self._configs.items():
            lock_key = f"{user_id}:{symbol}"
            lock = self._signal_locks.setdefault(lock_key, asyncio.Lock())
            if lock.locked():
                logger.debug("Signal skipped — already processing", user_id=user_id, symbol=symbol)
                continue
            try:
                async with lock:
                    await self._process_signal_for_user(user_id, config, signal_data)
            except Exception as e:
                logger.error(
                    "Error processing signal for user",
                    user_id=user_id, symbol=symbol, error=str(e),
                )

    async def _process_signal_for_user(
        self, user_id: str, config: AgentConfig, signal_data: dict
    ):
        raw_symbol = signal_data["symbol"]
        # Normalize: "BINANCE:BTCUSDT" → "BTCUSDT"
        symbol = raw_symbol.split(":")[-1] if ":" in raw_symbol else raw_symbol
        signal_data = {**signal_data, "symbol": symbol}

        if config.allowed_symbols and symbol not in config.allowed_symbols:
            return

        client = self._clients.get(user_id)
        if not client:
            logger.warning("No broker client for user", user_id=user_id, symbol=symbol)
            return

        logger.info("Processing signal", user_id=user_id, symbol=symbol,
                    signal=signal_data.get("signal"),
                    alert_level=signal_data.get("alert_level", "NORMAL"))

        try:
            account = await client.get_account()
        except Exception as e:
            logger.warning("Failed to get account", user_id=user_id, error=str(e))
            await self._alerter.send(
                self._http_client, "WARNING",
                "Broker connection error",
                f"Could not fetch account for {symbol}: {e}",
                user_id=user_id,
            )
            return

        self._risk_mgr.update_equity(user_id, account.equity)

        # ── Strategy Architect: guardian → engine → Claude ───────────────────
        result = await self._architect.evaluate(
            user_id=user_id,
            config=config,
            signal_data=signal_data,
            account=account,
            pool=self._pool,
            http_client=self._http_client,
            questdb_url=self._settings.questdb_url,
            risk_profile=self._risk_profiles.get(user_id),
        )
        decision    = result.decision
        claude_rec  = result.claude_rec
        original_action = decision.action

        logger.info(
            "Architect result",
            user_id=user_id, symbol=symbol,
            action=decision.action,
            guardian_vetoed=result.guardian_result.vetoed,
            claude_rec=claude_rec.recommendation,
            claude_conf=round(claude_rec.confidence, 3),
            latency_ms=round(claude_rec.latency_ms),
        )

        # Persist to QuestDB time-series
        await self._persist_claude_to_questdb(user_id, symbol, decision, claude_rec)

        # ── Execution Specialist: place order ────────────────────────────────
        broker_order_id = None
        status = "SKIPPED"

        if decision.action == "OPEN_LONG":
            exec_result = await self._executor.open_long(
                user_id=user_id, symbol=symbol,
                quantity=decision.quantity,
                signal_data=signal_data, claude_rec=claude_rec,
                client=client, pool=self._pool,
                conn_id=self._conn_ids.get(user_id),
                tracker=self._tracker, scorer=self._scorer,
                claude_decision_id=result.claude_decision_id,
            )
            status          = exec_result.status
            broker_order_id = exec_result.broker_order_id
            if self._pool and result.claude_decision_id and exec_result.status == "FAILED":
                try:
                    await self._pool.execute(
                        'UPDATE "ClaudeDecision" SET "executionStatus" = $1 WHERE id = $2',
                        "FAILED", result.claude_decision_id,
                    )
                except Exception:
                    pass

        elif decision.action == "CLOSE":
            exec_result = await self._executor.close_long(
                user_id=user_id, symbol=symbol,
                quantity=decision.quantity,
                signal_data=signal_data, claude_rec=claude_rec,
                client=client, pool=self._pool,
                conn_id=self._conn_ids.get(user_id),
                tracker=self._tracker, risk_mgr=self._risk_mgr,
                scorer=self._scorer,
            )
            status          = exec_result.status
            broker_order_id = exec_result.broker_order_id

        elif decision.action == "OPEN_SHORT":
            exec_result = await self._executor.open_short(
                user_id=user_id, symbol=symbol,
                quantity=decision.quantity,
                signal_data=signal_data, claude_rec=claude_rec,
                client=client, pool=self._pool,
                conn_id=self._conn_ids.get(user_id),
                tracker=self._tracker, scorer=self._scorer,
                claude_decision_id=result.claude_decision_id,
            )
            status          = exec_result.status
            broker_order_id = exec_result.broker_order_id
            if self._pool and result.claude_decision_id and exec_result.status == "FAILED":
                try:
                    await self._pool.execute(
                        'UPDATE "ClaudeDecision" SET "executionStatus" = $1 WHERE id = $2',
                        "FAILED", result.claude_decision_id,
                    )
                except Exception:
                    pass

        elif decision.action == "CLOSE_SHORT":
            exec_result = await self._executor.close_short(
                user_id=user_id, symbol=symbol,
                quantity=decision.quantity,
                signal_data=signal_data, claude_rec=claude_rec,
                client=client, pool=self._pool,
                conn_id=self._conn_ids.get(user_id),
                tracker=self._tracker, risk_mgr=self._risk_mgr,
                scorer=self._scorer,
            )
            status          = exec_result.status
            broker_order_id = exec_result.broker_order_id

        # Publish decision to NATS
        await self._nats.publish(f"agent.decisions.{user_id}", {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "userId": user_id,
            "symbol": symbol,
            "exchange": signal_data.get("exchange", ""),
            "action": decision.action,
            "originalAction": original_action,
            "quantity": decision.quantity,
            "price": signal_data.get("current_price", 0),
            "reason": decision.reason,
            "brokerOrderId": broker_order_id,
            "status": status,
            "guardian": {
                "vetoed": result.guardian_result.vetoed,
                "severity": result.guardian_result.severity,
                "reason": result.guardian_result.reason,
            },
            "claude": {
                "recommendation": claude_rec.recommendation,
                "confidence": round(claude_rec.confidence, 3),
                "expectedReturn": round(claude_rec.expected_return_pct, 4),
                "riskRewardRatio": round(claude_rec.risk_reward_ratio, 2),
                "reasoning": claude_rec.reasoning[:200],
                "latencyMs": round(claude_rec.latency_ms),
            },
        })

    # ── Command handler ──────────────────────────────────────────

    async def _on_command(self, msg):
        try:
            data = json.loads(msg.data.decode())
        except Exception:
            return

        action = data.get("action", "")
        # Extract user_id from subject: agent.command.{userId}
        parts = msg.subject.split(".")
        if len(parts) < 3:
            return
        user_id = parts[2]

        logger.info("Received command", user_id=user_id, action=action)

        if action == "pause":
            self._configs.pop(user_id, None)
        elif action == "resume":
            await self._reload_configs()
        elif action == "close_all":
            await self._close_all_positions(user_id)

    async def _close_all_positions(self, user_id: str):
        client = self._clients.get(user_id)
        if not client:
            return

        positions = self._tracker.get_all_positions(user_id)
        for pos in positions:
            try:
                await client.close_position(pos.symbol)
                self._tracker.record_close(user_id, pos.symbol)
                logger.info("Force-closed position", user_id=user_id, symbol=pos.symbol)
            except Exception as e:
                logger.error(
                    "Failed to force-close",
                    user_id=user_id, symbol=pos.symbol, error=str(e),
                )

    # ── Background tasks ─────────────────────────────────────────

    async def _reload_configs(self):
        if not self._pool:
            return
        try:
            configs = await load_all_agent_configs(self._pool)
            new_configs = {}
            for c in configs:
                new_configs[c.user_id] = c

                # Build broker client if new or changed
                if c.user_id not in self._clients:
                    conn = await load_broker_connection(
                        self._pool, c.user_id, c.broker
                    )
                    if conn:
                        try:
                            api_key = decrypt(conn.encrypted_key, self._settings.encryption_key)
                            api_secret = decrypt(conn.encrypted_secret, self._settings.encryption_key)
                            extra = {}
                            if conn.encrypted_extra:
                                extra = json.loads(
                                    decrypt(conn.encrypted_extra, self._settings.encryption_key)
                                )
                            self._clients[c.user_id] = create_broker_client(
                                c.broker, api_key, api_secret, extra
                            )
                            self._conn_ids[c.user_id] = conn.id
                        except Exception as e:
                            logger.error(
                                "Failed to create broker client",
                                user_id=c.user_id, error=str(e),
                            )

            # Load risk profiles for active users
            new_risk_profiles = {}
            for user_id in new_configs:
                try:
                    profile = await get_risk_profile(self._pool, user_id)
                    if profile:
                        new_risk_profiles[user_id] = profile
                except Exception as e:
                    logger.warning("Failed to load risk profile", user_id=user_id, error=str(e))
            self._risk_profiles = new_risk_profiles

            # Clean up removed users
            removed = set(self._configs.keys()) - set(new_configs.keys())
            for uid in removed:
                self._clients.pop(uid, None)
                self._conn_ids.pop(uid, None)

            self._configs = new_configs
            logger.info("Configs reloaded", active_users=len(self._configs))
        except Exception as e:
            logger.error("Config reload failed", error=str(e))

    async def _config_reload_loop(self):
        while self._running:
            await asyncio.sleep(self._settings.config_reload_interval_s)
            await self._reload_configs()

    async def _position_sync_loop(self):
        while self._running:
            await asyncio.sleep(self._settings.position_sync_interval_s)
            for user_id, client in self._clients.items():
                await self._tracker.sync_from_broker(user_id, client)
                # Also update equity
                try:
                    account = await client.get_account()
                    self._risk_mgr.update_equity(user_id, account.equity)
                except Exception:
                    pass

    async def _status_publish_loop(self):
        _alerted: dict[str, set] = {}  # user_id -> set of already-fired alert keys
        while self._running:
            await asyncio.sleep(30)
            for user_id, config in self._configs.items():
                state = self._risk_mgr.get_state(user_id)
                drawdown = 0.0
                if state.peak_equity > 0:
                    drawdown = (state.peak_equity - state.current_equity) / state.peak_equity * 100

                fired = _alerted.setdefault(user_id, set())

                # Daily loss limit alert (once per day per user)
                if (state.daily_realized_pnl <= -config.daily_loss_limit_usd
                        and "daily_loss" not in fired):
                    fired.add("daily_loss")
                    await self._alerter.send(
                        self._http_client, "CRITICAL",
                        "Daily loss limit reached",
                        f"P&L: ${state.daily_realized_pnl:.2f} / limit: -${config.daily_loss_limit_usd:.2f}",
                        user_id=user_id,
                    )

                # Max drawdown alert (once per day per user)
                if (drawdown >= config.max_drawdown_pct
                        and "drawdown" not in fired):
                    fired.add("drawdown")
                    await self._alerter.send(
                        self._http_client, "CRITICAL",
                        "Max drawdown reached",
                        f"Drawdown: {drawdown:.1f}% / limit: {config.max_drawdown_pct:.1f}%",
                        user_id=user_id,
                    )

                await self._nats.publish(f"agent.status.{user_id}", {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "userId": user_id,
                    "status": "running",
                    "broker": config.broker,
                    "openPositions": self._tracker.get_open_count(user_id),
                    "maxPositions": config.max_concurrent_positions,
                    "dailyPnlUsd": round(state.daily_realized_pnl, 2),
                    "dailyLossLimitUsd": config.daily_loss_limit_usd,
                    "drawdownPct": round(drawdown, 2),
                    "maxDrawdownPct": config.max_drawdown_pct,
                    "equity": round(state.current_equity, 2),
                    "peakEquity": round(state.peak_equity, 2),
                    "decisionsToday": state.decisions_today,
                    "tradesExecutedToday": state.trades_executed_today,
                    "uptime": int(time.time() - self._start_time),
                })

    async def _ensure_questdb_schema(self):
        """Create claude_decisions table in QuestDB if it doesn't exist."""
        query = (
            "CREATE TABLE IF NOT EXISTS claude_decisions ("
            "timestamp TIMESTAMP, "
            "user_id SYMBOL, "
            "symbol SYMBOL, "
            "action STRING, "
            "recommendation STRING, "
            "confidence DOUBLE, "
            "expected_return DOUBLE, "
            "expected_pnl DOUBLE, "
            "risk_reward_ratio DOUBLE, "
            "actual_pnl DOUBLE, "
            "outcome STRING, "
            "latency_ms INT"
            ") TIMESTAMP(timestamp) PARTITION BY DAY;"
        )
        questdb_url = self._settings.questdb_url
        for attempt in range(5):
            try:
                resp = await self._http_client.get(
                    f"{questdb_url}/exec", params={"query": query}
                )
                if resp.status_code == 200:
                    logger.info("QuestDB claude_decisions table ready")
                    return
            except Exception as e:
                logger.warning(
                    "QuestDB not ready for claude schema",
                    attempt=attempt, error=str(e),
                )
            await asyncio.sleep(2)

    async def _persist_claude_to_questdb(
        self, user_id: str, symbol: str, decision, claude_rec
    ):
        """Write Claude decision to QuestDB time-series (fire and forget)."""
        try:
            query = (
                f"INSERT INTO claude_decisions "
                f"(timestamp, user_id, symbol, action, recommendation, confidence, "
                f"expected_return, expected_pnl, risk_reward_ratio, latency_ms) VALUES ("
                f"now(), '{user_id}', '{symbol}', '{decision.action}', "
                f"'{claude_rec.recommendation}', {claude_rec.confidence}, "
                f"{claude_rec.expected_return_pct}, {claude_rec.expected_pnl}, "
                f"{claude_rec.risk_reward_ratio}, {int(claude_rec.latency_ms)});"
            )
            await self._http_client.get(
                f"{self._settings.questdb_url}/exec",
                params={"query": query},
            )
        except Exception as e:
            logger.debug("Failed to persist Claude to QuestDB", error=str(e))

    async def _health_server(self):
        """HTTP health check — returns JSON with real service status."""
        async def handle(reader, writer):
            await reader.read(1024)
            nats_ok = self._nats.is_connected
            db_ok   = self._pool is not None
            body = json.dumps({
                "status":         "ok" if (nats_ok and db_ok) else "degraded",
                "nats":           nats_ok,
                "db":             db_ok,
                "active_users":   len(self._configs),
                "open_positions": sum(
                    self._tracker.get_open_count(u) for u in self._configs
                ),
                "uptime_s":       int(time.time() - self._start_time),
            })
            http_status = "200 OK" if (nats_ok and db_ok) else "503 Service Unavailable"
            response = (
                f"HTTP/1.1 {http_status}\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n\r\n"
                f"{body}"
            )
            writer.write(response.encode())
            await writer.drain()
            writer.close()

        server = await asyncio.start_server(
            handle, "0.0.0.0", self._settings.health_port
        )
        logger.info("Health server listening", port=self._settings.health_port)
        async with server:
            await server.serve_forever()
