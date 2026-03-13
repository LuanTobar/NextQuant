"""
Alpaca Markets broker client — Python port of nextjs-frontend/src/lib/brokers/alpaca.ts.

Auth: simple API key headers (APCA-API-KEY-ID, APCA-API-SECRET-KEY).
"""

from typing import Any

import httpx

from .base import (
    AccountInfo,
    BrokerClient,
    OrderRequest,
    OrderResponse,
    Position,
)

ALPACA_URLS = {
    "paper": "https://paper-api.alpaca.markets",
    "live": "https://api.alpaca.markets",
}


class AlpacaClient(BrokerClient):
    broker = "ALPACA"

    def __init__(self, api_key: str, api_secret: str, environment: str = "paper"):
        self._base_url = ALPACA_URLS.get(environment, ALPACA_URLS["paper"])
        self._headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": api_secret,
            "Content-Type": "application/json",
        }
        self._client = httpx.AsyncClient(timeout=15)

    async def _fetch(self, path: str, method: str = "GET", body: dict | None = None) -> Any:
        kwargs: dict = {"headers": self._headers}
        if body:
            import json
            kwargs["content"] = json.dumps(body)

        resp = await self._client.request(method, f"{self._base_url}{path}", **kwargs)

        if not resp.is_success:
            err = resp.json() if resp.content else {}
            raise RuntimeError(
                f"Alpaca error ({resp.status_code}): {err.get('message', resp.reason_phrase)}"
            )
        if resp.status_code == 204:
            return {}
        return resp.json()

    def _normalize_status(self, status: str) -> str:
        return {
            "accepted": "new", "new": "new", "pending_new": "new",
            "partially_filled": "partially_filled",
            "filled": "filled", "done_for_day": "filled",
            "canceled": "cancelled", "expired": "cancelled", "replaced": "cancelled",
            "rejected": "rejected",
        }.get(status, status)

    def _to_order_response(self, data: dict) -> OrderResponse:
        return OrderResponse(
            broker_id=data["id"],
            symbol=data["symbol"],
            side=data["side"],
            quantity=float(data["qty"]),
            type=data.get("type", "market"),
            status=self._normalize_status(data["status"]),
            filled_qty=float(data["filled_qty"]) if data.get("filled_qty") else None,
            filled_avg_price=float(data["filled_avg_price"]) if data.get("filled_avg_price") else None,
            created_at=data.get("created_at", ""),
            raw=data,
        )

    # ── Orders ───────────────────────────────────────────────────

    async def place_order(self, req: OrderRequest) -> OrderResponse:
        body: dict = {
            "symbol": req.symbol,
            "qty": str(req.quantity),
            "side": req.side,
            "type": req.type,
            "time_in_force": req.time_in_force or "day",
        }
        if req.type == "limit" and req.limit_price:
            body["limit_price"] = str(req.limit_price)

        data = await self._fetch("/v2/orders", "POST", body)
        return self._to_order_response(data)

    async def get_order(self, broker_id: str) -> OrderResponse:
        data = await self._fetch(f"/v2/orders/{broker_id}")
        return self._to_order_response(data)

    async def cancel_order(self, broker_id: str) -> dict:
        try:
            await self._fetch(f"/v2/orders/{broker_id}", "DELETE")
            return {"success": True, "message": "Order cancelled"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def get_positions(self) -> list[Position]:
        data = await self._fetch("/v2/positions")
        positions = []
        for p in data:
            qty = abs(float(p["qty"]))
            current = float(p["current_price"])
            entry = float(p["avg_entry_price"])
            positions.append(Position(
                symbol=p["symbol"],
                quantity=qty,
                avg_entry_price=entry,
                current_price=current,
                market_value=float(p["market_value"]),
                unrealized_pl=float(p["unrealized_pl"]),
                unrealized_pl_pct=((current - entry) / entry * 100) if entry > 0 else 0,
                side="long" if float(p["qty"]) >= 0 else "short",
            ))
        return positions

    async def close_position(
        self, symbol: str, quantity: float | None = None
    ) -> OrderResponse:
        qs = f"?qty={quantity}" if quantity else ""
        data = await self._fetch(f"/v2/positions/{symbol}{qs}", "DELETE")
        return self._to_order_response(data)

    async def get_account(self) -> AccountInfo:
        data = await self._fetch("/v2/account")
        return AccountInfo(
            equity=float(data["equity"]),
            buying_power=float(data["buying_power"]),
            cash=float(data["cash"]),
            currency=data.get("currency", "USD"),
        )
