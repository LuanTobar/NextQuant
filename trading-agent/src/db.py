"""
PostgreSQL access via asyncpg — reads Prisma-managed tables directly.

Table names are PascalCase in double quotes (Prisma convention).
Column names are camelCase in double quotes.
"""

import json
from dataclasses import dataclass
from datetime import datetime

import asyncpg
import structlog

logger = structlog.get_logger()


@dataclass
class AgentConfig:
    id: str
    user_id: str
    enabled: bool
    broker: str
    max_position_size_usd: float
    max_concurrent_positions: int
    daily_loss_limit_usd: float
    max_drawdown_pct: float
    aggressiveness: float
    allowed_symbols: list[str]


@dataclass
class BrokerConnection:
    id: str
    user_id: str
    broker: str
    label: str | None
    encrypted_key: str
    encrypted_secret: str
    encrypted_extra: str | None
    is_active: bool


@dataclass
class PositionRisk:
    user_id: str
    broker: str
    symbol: str
    stop_loss_price: float | None
    take_profit_price: float | None
    is_active: bool


async def create_pool(database_url: str) -> asyncpg.Pool:
    pool = await asyncpg.create_pool(database_url, min_size=2, max_size=5)
    logger.info("PostgreSQL pool created")
    return pool


async def load_all_agent_configs(pool: asyncpg.Pool) -> list[AgentConfig]:
    rows = await pool.fetch(
        'SELECT * FROM "AgentConfig" WHERE enabled = true'
    )
    configs = []
    for r in rows:
        configs.append(AgentConfig(
            id=r["id"],
            user_id=r["userId"],
            enabled=r["enabled"],
            broker=r["broker"],
            max_position_size_usd=r["maxPositionSizeUsd"],
            max_concurrent_positions=r["maxConcurrentPositions"],
            daily_loss_limit_usd=r["dailyLossLimitUsd"],
            max_drawdown_pct=r["maxDrawdownPct"],
            aggressiveness=r["aggressiveness"],
            allowed_symbols=r["allowedSymbols"] or [],
        ))
    return configs


async def load_broker_connection(
    pool: asyncpg.Pool, user_id: str, broker: str
) -> BrokerConnection | None:
    row = await pool.fetchrow(
        'SELECT * FROM "BrokerConnection" '
        'WHERE "userId" = $1 AND broker = $2 AND "isActive" = true',
        user_id, broker,
    )
    if not row:
        return None
    return BrokerConnection(
        id=row["id"],
        user_id=row["userId"],
        broker=row["broker"],
        label=row["label"],
        encrypted_key=row["encryptedKey"],
        encrypted_secret=row["encryptedSecret"],
        encrypted_extra=row.get("encryptedExtra"),
        is_active=row["isActive"],
    )


async def save_order(
    pool: asyncpg.Pool,
    user_id: str,
    broker_connection_id: str,
    symbol: str,
    side: str,
    quantity: float,
    order_type: str,
    broker_order_id: str | None,
    broker_response: dict | None = None,
) -> str:
    """Insert an order record. Returns the order ID."""
    # Generate a cuid-like ID (simplified — 25 char random)
    import secrets
    order_id = "c" + secrets.token_hex(12)

    now = datetime.utcnow()
    await pool.execute(
        'INSERT INTO "Order" '
        '(id, "userId", "brokerConnectionId", symbol, side, quantity, '
        '"orderType", status, "brokerOrderId", "brokerResponse", "createdAt", "updatedAt") '
        'VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)',
        order_id, user_id, broker_connection_id, symbol,
        side.upper(), quantity, order_type, "PENDING",
        broker_order_id,
        json.dumps(broker_response) if broker_response else None,
        now, now,
    )
    return order_id


async def update_order_status(
    pool: asyncpg.Pool,
    order_id: str,
    status: str,
    filled_price: float | None = None,
    filled_quantity: float | None = None,
) -> None:
    await pool.execute(
        'UPDATE "Order" SET status = $1, "filledPrice" = $2, '
        '"filledQuantity" = $3, "updatedAt" = $4 WHERE id = $5',
        status, filled_price, filled_quantity, datetime.utcnow(), order_id,
    )


async def save_claude_decision(
    pool: asyncpg.Pool,
    user_id: str,
    symbol: str,
    action: str,
    signal_data: dict,
    claude_rec,  # ClaudeRecommendation dataclass
) -> str:
    """Insert a Claude decision record. Returns the decision ID."""
    import secrets
    decision_id = "c" + secrets.token_hex(12)
    now = datetime.utcnow()

    await pool.execute(
        'INSERT INTO "ClaudeDecision" '
        '(id, "userId", symbol, action, "mlSignal", "claudeAnalysis", '
        'recommendation, confidence, "expectedReturn", "expectedPnl", '
        '"riskRewardRatio", "adjustedSize", "executionStatus", "latencyMs", '
        '"createdAt") '
        'VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)',
        decision_id,
        user_id,
        symbol,
        action,
        json.dumps(signal_data),
        json.dumps({
            "execute": claude_rec.execute,
            "confidence": claude_rec.confidence,
            "reasoning": claude_rec.reasoning,
            "recommendation": claude_rec.recommendation,
            "expected_return_pct": claude_rec.expected_return_pct,
            "expected_pnl_usd": claude_rec.expected_pnl,
            "risk_reward_ratio": claude_rec.risk_reward_ratio,
            "fees_estimated_pct": claude_rec.fees_estimated,
        }),
        claude_rec.recommendation,
        claude_rec.confidence,
        claude_rec.expected_return_pct,
        claude_rec.expected_pnl,
        claude_rec.risk_reward_ratio,
        claude_rec.adjusted_size,
        "PENDING",
        int(claude_rec.latency_ms),
        now,
    )
    return decision_id


async def load_recent_signal_history(
    http_client, questdb_url: str, symbol: str, limit: int = 20
) -> list[dict]:
    """Load recent ML signal history from QuestDB for Claude context."""
    import urllib.parse
    query = (
        f"SELECT timestamp, signal, current_price, predicted_close, "
        f"regime, volatility, causal_effect, causal_description "
        f"FROM ml_signals WHERE symbol = '{symbol}' "
        f"ORDER BY timestamp DESC LIMIT {limit}"
    )
    try:
        url = f"{questdb_url}/exec"
        resp = await http_client.get(url, params={"query": query})
        if resp.status_code != 200:
            return []
        data = resp.json()
        columns = [c["name"] for c in data.get("columns", [])]
        result = []
        for row in data.get("dataset", []):
            result.append(dict(zip(columns, row)))
        return result
    except Exception as e:
        logger.warning("Failed to load signal history from QuestDB", error=str(e))
        return []


async def load_position_risks(
    pool: asyncpg.Pool, user_id: str, broker: str
) -> list[PositionRisk]:
    rows = await pool.fetch(
        'SELECT * FROM "PositionRisk" '
        'WHERE "userId" = $1 AND broker = $2 AND "isActive" = true',
        user_id, broker,
    )
    return [
        PositionRisk(
            user_id=r["userId"],
            broker=r["broker"],
            symbol=r["symbol"],
            stop_loss_price=r["stopLossPrice"],
            take_profit_price=r["takeProfitPrice"],
            is_active=r["isActive"],
        )
        for r in rows
    ]


async def get_risk_profile(pool: asyncpg.Pool, user_id: str) -> dict | None:
    """Return {risk_score, risk_category} for a user, or None if not set."""
    row = await pool.fetchrow(
        'SELECT "riskScore", "riskCategory" FROM "RiskProfile" WHERE "userId" = $1',
        user_id,
    )
    if not row:
        return None
    return {
        "risk_score":    float(row["riskScore"]),
        "risk_category": row["riskCategory"],
    }
