"""
In-memory position tracking with periodic broker sync.
"""

import structlog
from .brokers.base import BrokerClient, Position

logger = structlog.get_logger()


class PositionTracker:
    def __init__(self):
        # {user_id: {symbol: Position}}
        self._positions: dict[str, dict[str, Position]] = {}

    # Minimum value to count as a real position (ignore dust)
    DUST_THRESHOLD_USD = 1.0

    def get_open_count(self, user_id: str) -> int:
        return sum(
            1 for p in self._positions.get(user_id, {}).values()
            if p.market_value >= self.DUST_THRESHOLD_USD
        )

    def get_position(self, user_id: str, symbol: str) -> Position | None:
        pos = self._positions.get(user_id, {}).get(symbol)
        if pos and pos.market_value < self.DUST_THRESHOLD_USD:
            return None  # Dust — ignore
        return pos

    def get_all_positions(self, user_id: str) -> list[Position]:
        return list(self._positions.get(user_id, {}).values())

    def get_total_value(self, user_id: str) -> float:
        return sum(p.market_value for p in self._positions.get(user_id, {}).values())

    def record_open(self, user_id: str, symbol: str, qty: float, price: float, side: str = "long") -> None:
        if user_id not in self._positions:
            self._positions[user_id] = {}
        self._positions[user_id][symbol] = Position(
            symbol=symbol, quantity=qty, avg_entry_price=price,
            current_price=price, market_value=qty * price,
            unrealized_pl=0, side=side,
        )

    def record_close(self, user_id: str, symbol: str) -> None:
        if user_id in self._positions:
            self._positions[user_id].pop(symbol, None)

    async def sync_from_broker(self, user_id: str, client: BrokerClient) -> None:
        """Sync in-memory positions with broker's actual positions.
        Preserves avg_entry_price from agent-opened positions (broker returns 0)."""
        try:
            positions = await client.get_positions()
            existing = self._positions.get(user_id, {})
            new_map = {}
            for p in positions:
                old = existing.get(p.symbol)
                # Preserve our tracked entry price if broker doesn't provide one
                if old and old.avg_entry_price > 0 and p.avg_entry_price == 0:
                    p = Position(
                        symbol=p.symbol, quantity=p.quantity,
                        avg_entry_price=old.avg_entry_price,
                        current_price=p.current_price,
                        market_value=p.market_value,
                        unrealized_pl=((p.current_price - old.avg_entry_price)
                                       * p.quantity) if old.avg_entry_price > 0 else 0,
                        side=p.side,
                    )
                new_map[p.symbol] = p
            self._positions[user_id] = new_map
            logger.debug(
                "Positions synced",
                user_id=user_id, count=len(positions),
            )
        except Exception as e:
            logger.warning(
                "Position sync failed",
                user_id=user_id, error=str(e),
            )
