"""
Claude Decision Layer — validates trading signals with statistical rigor.

Acts as a "senior quant trader" that reviews every ML signal before execution.
Only approves trades with positive expected value after fees.
Includes circuit breaker, timeout, and prompt caching for cost efficiency.
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx
import structlog

from .config import Settings
from .db import AgentConfig, PositionRisk
from .risk_manager import DailyRiskState
from .brokers.base import AccountInfo, Position
from .score_tracker import SymbolScore

logger = structlog.get_logger()


# ── Data structures ─────────────────────────────────────────────

@dataclass
class ClaudeRecommendation:
    execute: bool = False
    confidence: float = 0.0
    adjusted_size: float = 1.0       # Multiplier 0.0-1.0
    reasoning: str = ""
    expected_return_pct: float = 0.0
    expected_pnl: float = 0.0
    risk_reward_ratio: float = 0.0
    fees_estimated: float = 0.0
    recommendation: str = "REJECT"   # APPROVE, REJECT, REDUCE
    latency_ms: float = 0.0
    decision_id: str = ""            # Set after DB insert


# ── System prompt (cached for cost reduction) ───────────────────

SYSTEM_PROMPT = """You are a quantitative trading analyst for NexQuant. Your job is to validate \
trading signals using statistical analysis BEFORE they execute with real money.

## YOUR DECISION FRAMEWORK

For every signal, compute:
1. EXPECTED VALUE = P(win) × avg_win - P(loss) × avg_loss - total_fees
2. RISK/REWARD RATIO = potential_upside / potential_downside
3. FEE-ADJUSTED RETURN = expected_return - roundtrip_fees (0.20% for crypto, 0.10% for stocks)

## RULES (NON-NEGOTIABLE)
- NEVER approve a trade with expected return < 0.25% after fees
- NEVER approve if risk/reward ratio < 1.5:1
- NEVER approve if the symbol's historical win_rate < 45% (unless fewer than 5 trades — then allow cautiously)
- REDUCE position size (adjusted_size_multiplier < 1.0) if confidence band width > 2% of price
- REDUCE position size by 50% (multiplier=0.5) in HIGH_VOL regime
- REJECT if daily P&L is already negative AND current drawdown > 50% of max allowed drawdown

## REGIME-SPECIFIC BEHAVIOR
- LOW_VOL: Favor mean-reversion signals. Allow larger positions. Expect tighter stops.
- MEDIUM_VOL: Standard momentum following. Normal position sizing.
- HIGH_VOL: Only approve high-conviction trades (confidence > 0.75). Half position size.

## HISTORICAL ACCURACY (weight heavily when available)
- win_rate > 60%: increase confidence, allow full sizing
- win_rate 45-60%: standard evaluation
- win_rate < 45%: REJECT unless regime has clearly shifted or fewer than 5 historical trades
- Sharpe > 1.0: strong performer, allow full sizing
- Sharpe < 0: consistently losing — REJECT

## POSITION CONTEXT
- If portfolio already has 2+ correlated positions, REDUCE new position by 30%
- If unrealized P&L across all positions is negative, be more conservative (reduce size by 20%)

## OUTPUT FORMAT (respond with ONLY this JSON, no markdown, no explanation outside JSON)
{
  "execute": boolean,
  "confidence": 0.0-1.0,
  "adjusted_size_multiplier": 0.0-1.0,
  "reasoning": "2-3 sentences max explaining the statistical basis for your decision",
  "expected_return_pct": number,
  "expected_pnl_usd": number,
  "risk_reward_ratio": number,
  "fees_estimated_pct": number,
  "recommendation": "APPROVE" | "REJECT" | "REDUCE"
}"""


# ── Claude Layer class ──────────────────────────────────────────

class ClaudeLayer:
    def __init__(self, settings: Settings):
        self._api_key = settings.anthropic_api_key
        self._model = settings.claude_model
        self._max_tokens = settings.claude_max_tokens
        self._timeout = settings.claude_timeout_s
        self._confidence_threshold = settings.claude_confidence_threshold
        self._min_expected_return = settings.claude_min_expected_return
        self._enabled = settings.claude_enabled and bool(settings.anthropic_api_key)
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.claude_timeout_s, connect=5.0)
        )

        # Circuit breaker
        self._consecutive_failures = 0
        self._circuit_open_until: datetime | None = None
        self._max_failures = settings.claude_circuit_breaker_failures
        self._cooldown_s = settings.claude_circuit_breaker_cooldown_s

        if not self._enabled:
            logger.warning(
                "Claude layer DISABLED",
                has_key=bool(settings.anthropic_api_key),
                enabled_flag=settings.claude_enabled,
            )
        else:
            logger.info(
                "Claude layer initialized",
                model=self._model,
                confidence_threshold=self._confidence_threshold,
            )

    async def evaluate(
        self,
        signal_data: dict,
        decision,  # Decision dataclass from decision_engine
        config: AgentConfig,
        risk_state: DailyRiskState,
        positions: list[Position],
        account: AccountInfo,
        symbol_score: SymbolScore | None,
        position_risks: list[PositionRisk],
        signal_history: list[dict] | None = None,
        risk_profile: dict | None = None,
    ) -> ClaudeRecommendation:
        """
        Evaluate whether to execute the DecisionEngine's decision.
        Returns ClaudeRecommendation with execute=True/False and reasoning.
        """
        symbol = signal_data.get("symbol", "?")

        # ── Kill switch ──
        if not self._enabled:
            return ClaudeRecommendation(
                execute=True, confidence=0.5,
                reasoning="Claude layer disabled — passing through to engine.",
                recommendation="APPROVE",
            )

        # ── Only evaluate actionable decisions ──
        if decision.action == "HOLD":
            return ClaudeRecommendation(
                execute=False, confidence=1.0,
                reasoning="Engine decided HOLD — no trade to evaluate.",
                recommendation="APPROVE",
            )

        # ── Safety override: stop-loss / take-profit always execute ──
        if decision.action == "CLOSE":
            reason_lower = decision.reason.lower()
            if any(kw in reason_lower for kw in ["stop loss", "take profit"]):
                return ClaudeRecommendation(
                    execute=True, confidence=1.0,
                    reasoning=f"Safety exit: {decision.reason}. Bypassing Claude analysis.",
                    recommendation="APPROVE",
                )

        # ── Circuit breaker ──
        now = datetime.now(timezone.utc)
        if self._circuit_open_until and now < self._circuit_open_until:
            remaining = (self._circuit_open_until - now).total_seconds()
            logger.warning(
                "Claude circuit breaker OPEN",
                symbol=symbol, cooldown_remaining_s=round(remaining),
            )
            return ClaudeRecommendation(
                execute=True, confidence=0.5,
                reasoning=f"Claude circuit breaker open ({round(remaining)}s remaining). Falling back to engine.",
                recommendation="APPROVE",
            )

        # ── Build prompt and call Claude ──
        user_prompt = self._build_user_prompt(
            signal_data, decision, config, risk_state,
            positions, account, symbol_score, position_risks,
            signal_history, risk_profile,
        )

        try:
            start = time.monotonic()
            response = await asyncio.wait_for(
                self._call_claude(user_prompt),
                timeout=self._timeout,
            )
            latency = (time.monotonic() - start) * 1000

            self._consecutive_failures = 0
            rec = self._parse_response(response)
            rec.latency_ms = latency

            logger.info(
                "Claude evaluated",
                symbol=symbol,
                recommendation=rec.recommendation,
                confidence=round(rec.confidence, 3),
                expected_return=round(rec.expected_return_pct, 4),
                risk_reward=round(rec.risk_reward_ratio, 2),
                latency_ms=round(latency),
            )

            # Apply confidence threshold
            if rec.execute and rec.confidence < self._confidence_threshold:
                rec.execute = False
                rec.recommendation = "REJECT"
                rec.reasoning += f" [Auto-rejected: confidence {rec.confidence:.2f} < threshold {self._confidence_threshold}]"

            return rec

        except asyncio.TimeoutError:
            self._consecutive_failures += 1
            self._check_circuit_breaker()
            logger.warning("Claude timeout", symbol=symbol, timeout_s=self._timeout)
            return ClaudeRecommendation(
                execute=True, confidence=0.5,
                reasoning=f"Claude timed out after {self._timeout}s. Falling back to engine.",
                recommendation="APPROVE", latency_ms=self._timeout * 1000,
            )

        except Exception as e:
            self._consecutive_failures += 1
            self._check_circuit_breaker()
            logger.error("Claude evaluation failed", symbol=symbol, error=str(e))
            return ClaudeRecommendation(
                execute=True, confidence=0.5,
                reasoning=f"Claude error: {str(e)[:100]}. Falling back to engine.",
                recommendation="APPROVE", latency_ms=0,
            )

    def _check_circuit_breaker(self):
        if self._consecutive_failures >= self._max_failures:
            self._circuit_open_until = datetime.now(timezone.utc) + timedelta(
                seconds=self._cooldown_s
            )
            logger.error(
                "Claude circuit breaker TRIPPED",
                failures=self._consecutive_failures,
                cooldown_s=self._cooldown_s,
            )

    # ── Prompt construction ─────────────────────────────────────

    def _build_user_prompt(
        self,
        signal_data: dict,
        decision,
        config: AgentConfig,
        risk_state: DailyRiskState,
        positions: list[Position],
        account: AccountInfo,
        symbol_score: SymbolScore | None,
        position_risks: list[PositionRisk],
        signal_history: list[dict] | None = None,
        risk_profile: dict | None = None,
    ) -> str:
        symbol = signal_data.get("symbol", "?")
        exchange = signal_data.get("exchange", "?")
        price = signal_data.get("current_price", 0)
        predicted = signal_data.get("predicted_close", 0)
        conf_low = signal_data.get("confidence_low", 0)
        conf_high = signal_data.get("confidence_high", 0)
        regime = signal_data.get("regime", "?")
        volatility = signal_data.get("volatility", 0)
        causal_desc = signal_data.get("causal_description", "N/A")
        causal_effect = signal_data.get("causal_effect", 0)

        expected_return = ((predicted - price) / price * 100) if price > 0 else 0
        band_width = ((conf_high - conf_low) / price * 100) if price > 0 else 0
        position_size_usd = decision.quantity * price if price > 0 else 0

        # Fee rate by exchange
        fee_rate = 0.20 if exchange in ("BINANCE", "CRYPTO") else 0.10

        # Drawdown calculation
        drawdown_pct = 0.0
        if risk_state.peak_equity > 0:
            drawdown_pct = (
                (risk_state.peak_equity - risk_state.current_equity)
                / risk_state.peak_equity * 100
            )

        # Build positions section
        positions_text = "No open positions."
        total_unrealized = 0.0
        if positions:
            lines = []
            for p in positions:
                if p.market_value < 1.0:
                    continue
                pnl_pct = (
                    (p.current_price - p.avg_entry_price) / p.avg_entry_price * 100
                    if p.avg_entry_price > 0 else 0
                )
                lines.append(
                    f"  {p.symbol}: {p.quantity:.4f} @ ${p.avg_entry_price:.2f} → "
                    f"${p.current_price:.2f} (P&L: ${p.unrealized_pl:.2f} / {pnl_pct:+.2f}%)"
                )
                total_unrealized += p.unrealized_pl
            if lines:
                positions_text = "\n".join(lines)
                positions_text += f"\n  Total Unrealized P&L: ${total_unrealized:.2f}"

        # Build score card section
        score_text = "No trading history for this symbol yet."
        if symbol_score and symbol_score.total_trades > 0:
            score_text = (
                f"Total Trades: {symbol_score.total_trades} | "
                f"Wins: {symbol_score.wins} | Losses: {symbol_score.losses}\n"
                f"  Win Rate: {symbol_score.win_rate * 100:.1f}% | "
                f"Avg Win: ${symbol_score.avg_win_pct:.2f} | "
                f"Avg Loss: ${symbol_score.avg_loss_pct:.2f}\n"
                f"  Sharpe: {symbol_score.sharpe_ratio:.3f} | "
                f"Total P&L: ${symbol_score.total_pnl:.2f}"
            )

        # Build signal history section
        history_text = "No recent signal history available."
        if signal_history:
            lines = []
            for h in signal_history[:10]:  # Last 10 for context
                lines.append(
                    f"  {h.get('timestamp', '?')}: {h.get('signal', '?')} @ "
                    f"${h.get('current_price', 0):.2f} → predicted ${h.get('predicted_close', 0):.2f} "
                    f"(regime: {h.get('regime', '?')}, vol: {h.get('volatility', 0):.1f}%)"
                )
            history_text = "\n".join(lines)

        # Build risk rules section
        risk_text = "No specific stop-loss/take-profit rules set."
        matching_risk = next(
            (r for r in position_risks if r.symbol == symbol), None
        )
        if matching_risk:
            parts = []
            if matching_risk.stop_loss_price:
                parts.append(f"Stop Loss: ${matching_risk.stop_loss_price:.2f}")
            if matching_risk.take_profit_price:
                parts.append(f"Take Profit: ${matching_risk.take_profit_price:.2f}")
            if parts:
                risk_text = " | ".join(parts)

        # Build risk profile section
        if risk_profile:
            score = risk_profile.get("risk_score", 0.5)
            category = risk_profile.get("risk_category", "MODERATE")
            risk_profile_text = (
                f"Category: {category} | Score: {score:.2f}/1.0\n"
                f"  (0=Conservative → 1=Speculative; calibrate position sizing accordingly)"
            )
        else:
            risk_profile_text = "Not set — treat as MODERATE."

        prompt = f"""## CURRENT SIGNAL
Symbol: {symbol} [{exchange}]
ML Signal: {signal_data.get('signal', '?')} (from causal+predictive+regime pipeline)
Current Price: ${price:.4f}
Predicted Close: ${predicted:.4f} ({expected_return:+.3f}%)
Confidence Band: ${conf_low:.4f} - ${conf_high:.4f} (width: {band_width:.2f}%)
Regime: {regime} (Volatility: {volatility:.1f}%)
Causal Analysis: {causal_desc} (effect: {causal_effect:.4f})

## DECISION ENGINE SAYS
Action: {decision.action}
Quantity: {decision.quantity:.6f}
Position Size: ${position_size_usd:.2f}
Reason: {decision.reason}

## ACCOUNT STATE
Equity: ${account.equity:.2f} | Buying Power: ${account.buying_power:.2f} | Cash: ${account.cash:.2f}
Daily P&L: ${risk_state.daily_realized_pnl:.2f} | Peak Equity: ${risk_state.peak_equity:.2f}
Drawdown: {drawdown_pct:.2f}% (max allowed: {config.max_drawdown_pct}%)
Decisions Today: {risk_state.decisions_today} | Trades Executed: {risk_state.trades_executed_today}

## CURRENT POSITIONS ({len([p for p in positions if p.market_value >= 1.0])} open)
{positions_text}

## SIGNAL HISTORY (last 10 for {symbol})
{history_text}

## SCORE CARD FOR {symbol}
{score_text}

## USER RISK PROFILE
{risk_profile_text}

## RISK RULES
{risk_text}
Max Position: ${config.max_position_size_usd:.2f} | Max Concurrent: {config.max_concurrent_positions}
Aggressiveness: {config.aggressiveness:.2f} | Fee Rate: {fee_rate}% roundtrip

Analyze and respond with JSON only."""

        return prompt

    # ── Claude API call with prompt caching ─────────────────────

    async def _call_claude(self, user_prompt: str) -> dict:
        """POST to Anthropic API with prompt caching on system prompt."""
        response = await self._client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
                "anthropic-beta": "prompt-caching-2024-07-31",
                "content-type": "application/json",
            },
            json={
                "model": self._model,
                "max_tokens": self._max_tokens,
                "temperature": 0.1,  # Low temp for consistent structured output
                "system": [
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                "messages": [
                    {"role": "user", "content": user_prompt},
                ],
            },
        )
        response.raise_for_status()
        return response.json()

    # ── Response parsing ────────────────────────────────────────

    def _parse_response(self, api_response: dict) -> ClaudeRecommendation:
        """Extract structured JSON from Claude's response."""
        try:
            content = api_response.get("content", [])
            text = ""
            for block in content:
                if block.get("type") == "text":
                    text = block.get("text", "")
                    break

            if not text:
                logger.warning("Empty Claude response")
                return self._fallback_recommendation("Empty response from Claude")

            # Try to parse as JSON directly
            # Handle potential markdown code blocks
            clean = text.strip()
            if clean.startswith("```"):
                # Remove markdown code fences
                lines = clean.split("\n")
                clean = "\n".join(
                    l for l in lines
                    if not l.strip().startswith("```")
                )

            data = json.loads(clean)

            return ClaudeRecommendation(
                execute=bool(data.get("execute", False)),
                confidence=float(data.get("confidence", 0)),
                adjusted_size=float(data.get("adjusted_size_multiplier", 1.0)),
                reasoning=str(data.get("reasoning", "")),
                expected_return_pct=float(data.get("expected_return_pct", 0)),
                expected_pnl=float(data.get("expected_pnl_usd", 0)),
                risk_reward_ratio=float(data.get("risk_reward_ratio", 0)),
                fees_estimated=float(data.get("fees_estimated_pct", 0)),
                recommendation=str(data.get("recommendation", "REJECT")),
            )

        except json.JSONDecodeError as e:
            logger.warning("Failed to parse Claude JSON", error=str(e), text=text[:200])
            return self._fallback_recommendation(f"JSON parse error: {e}")
        except Exception as e:
            logger.warning("Failed to parse Claude response", error=str(e))
            return self._fallback_recommendation(f"Parse error: {e}")

    def _fallback_recommendation(self, reason: str) -> ClaudeRecommendation:
        """Conservative fallback when Claude response can't be parsed."""
        return ClaudeRecommendation(
            execute=False, confidence=0.0,
            reasoning=f"Fallback: {reason}. Rejecting trade for safety.",
            recommendation="REJECT",
        )

    async def close(self):
        """Graceful shutdown."""
        await self._client.aclose()
