from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class OrderRequest:
    symbol: str
    side: str           # "buy" | "sell"
    quantity: float
    type: str           # "market" | "limit"
    time_in_force: str = "day"
    limit_price: float | None = None


@dataclass
class OrderResponse:
    broker_id: str
    symbol: str
    side: str
    quantity: float
    type: str
    status: str         # "new" | "partially_filled" | "filled" | "cancelled" | "rejected"
    filled_qty: float | None = None
    filled_avg_price: float | None = None
    created_at: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class AccountInfo:
    equity: float
    buying_power: float
    cash: float
    currency: str


@dataclass
class Position:
    symbol: str
    quantity: float
    avg_entry_price: float
    current_price: float
    market_value: float
    unrealized_pl: float
    unrealized_pl_pct: float = 0.0
    side: str = "long"


class BrokerClient(ABC):
    broker: str = ""

    @abstractmethod
    async def place_order(self, req: OrderRequest) -> OrderResponse: ...

    @abstractmethod
    async def get_order(self, broker_id: str) -> OrderResponse: ...

    @abstractmethod
    async def cancel_order(self, broker_id: str) -> dict: ...

    @abstractmethod
    async def get_positions(self) -> list[Position]: ...

    @abstractmethod
    async def close_position(
        self, symbol: str, quantity: float | None = None
    ) -> OrderResponse: ...

    @abstractmethod
    async def get_account(self) -> AccountInfo: ...
