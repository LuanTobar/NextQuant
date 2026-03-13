"""
Bitget spot broker client — Python port of nextjs-frontend/src/lib/brokers/bitget.ts.

Auth: HMAC-SHA256 request signing.
  prehash = timestamp + METHOD + requestPath + body
  signature = base64( HMAC-SHA256( prehash, apiSecret ) )
"""

import asyncio
import base64
import hashlib
import hmac
import time
from typing import Any

import httpx
import structlog

from .base import (
    AccountInfo,
    BrokerClient,
    OrderRequest,
    OrderResponse,
    Position,
)

BITGET_BASE = "https://api.bitget.com"

logger = structlog.get_logger()

# Known base-asset precision (max decimals for quantity/size) on Bitget spot.
# Bitget returns error 40808 "checkBDScale" when size has more decimals than allowed.
# We truncate (floor) instead of rounding to avoid exceeding available balance.
QUANTITY_PRECISION: dict[str, int] = {
    "BTCUSDT": 6,
    "ETHUSDT": 4,
    "SOLUSDT": 4,
    "XRPUSDT": 2,
    "DOGEUSDT": 2,
    "ADAUSDT": 2,
    "MANAUSDT": 2,
    "BNBUSDT": 5,
    "AVAXUSDT": 4,
    "DOTUSDT": 4,
    "MATICUSDT": 2,
    "LINKUSDT": 4,
    "LTCUSDT": 5,
}
DEFAULT_PRECISION = 4


def _truncate_qty(symbol: str, qty: float) -> float:
    """Truncate quantity to Bitget's allowed decimal precision."""
    decimals = QUANTITY_PRECISION.get(symbol, DEFAULT_PRECISION)
    factor = 10 ** decimals
    import math
    return math.floor(qty * factor) / factor


class BitgetClient(BrokerClient):
    broker = "BITGET"

    def __init__(self, api_key: str, api_secret: str, passphrase: str, simulated: bool = False):
        self._api_key = api_key
        self._api_secret = api_secret
        self._passphrase = passphrase
        self._simulated = simulated
        self._client = httpx.AsyncClient(timeout=15)

    # ── Signing ──────────────────────────────────────────────────

    def _sign(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        prehash = timestamp + method.upper() + path + body
        mac = hmac.new(
            self._api_secret.encode(), prehash.encode(), hashlib.sha256
        )
        return base64.b64encode(mac.digest()).decode()

    # ── HTTP layer ───────────────────────────────────────────────

    async def _request(self, method: str, path: str, body: dict | None = None) -> Any:
        timestamp = str(int(time.time() * 1000))
        body_str = ""
        if body:
            import json
            body_str = json.dumps(body)

        signature = self._sign(timestamp, method, path, body_str)

        headers = {
            "ACCESS-KEY": self._api_key,
            "ACCESS-SIGN": signature,
            "ACCESS-TIMESTAMP": timestamp,
            "ACCESS-PASSPHRASE": self._passphrase,
            "Content-Type": "application/json",
            "locale": "en-US",
        }

        resp = await self._client.request(
            method,
            f"{BITGET_BASE}{path}",
            headers=headers,
            content=body_str if body_str else None,
        )
        data = resp.json()

        if data.get("code") != "00000":
            raise RuntimeError(
                f"Bitget API error ({data.get('code')}): {data.get('msg', 'Unknown')}"
            )
        return data.get("data")

    async def _get_ticker_price(self, symbol: str) -> float:
        """Public endpoint — no auth. Fetch current price."""
        resp = await self._client.get(
            f"{BITGET_BASE}/api/v2/spot/market/tickers",
            params={"symbol": symbol},
        )
        data = resp.json()
        if data.get("code") != "00000" or not data.get("data"):
            return 0.0
        return float(data["data"][0].get("lastPr", 0))

    def _normalize_status(self, bg_status: str) -> str:
        return {
            "init": "new", "new": "new", "live": "new",
            "partially_filled": "partially_filled",
            "filled": "filled",
            "cancelled": "cancelled", "canceled": "cancelled",
        }.get(bg_status.lower(), bg_status)

    def _to_order_response(self, o: dict) -> OrderResponse:
        return OrderResponse(
            broker_id=o["orderId"],
            symbol=o.get("symbol", ""),
            side=o.get("side", "").lower(),
            quantity=float(o.get("size", 0)),
            type="limit" if o.get("orderType") == "limit" else "market",
            status=self._normalize_status(o.get("status", "")),
            filled_qty=float(o["baseVolume"]) if o.get("baseVolume") else None,
            filled_avg_price=float(o["priceAvg"]) if o.get("priceAvg") else None,
            created_at=o.get("cTime", ""),
            raw=o,
        )

    # ── Orders ───────────────────────────────────────────────────

    async def place_order(self, req: OrderRequest) -> OrderResponse:
        size_value = _truncate_qty(req.symbol, req.quantity)

        if self._simulated:
            # Futures (mix) order: tradeSide open for buy, close for sell
            body: dict = {
                "symbol": req.symbol,
                "productType": "USDT-FUTURES",
                "marginMode": "crossed",
                "marginCoin": "USDT",
                "size": str(size_value),
                "side": req.side,
                "tradeSide": "open" if req.side.lower() == "buy" else "close",
                "orderType": req.type,
                "force": req.time_in_force or "gtc",
            }
            if req.type == "limit" and req.limit_price:
                body["price"] = str(req.limit_price)
            data = await self._request("POST", "/api/v2/mix/order/place-order", body)
        else:
            # Spot order: market BUY size must be in USDT
            if req.type == "market" and req.side.lower() == "buy":
                price = await self._get_ticker_price(req.symbol)
                if price > 0:
                    size_value = round(req.quantity * price, 2)
                else:
                    raise RuntimeError(f"Cannot get price for {req.symbol} to place market buy")
                logger.info(
                    "Market BUY size in USDT",
                    symbol=req.symbol, base_qty=req.quantity,
                    price=price, usdt_size=size_value,
                )

            body = {
                "symbol": req.symbol,
                "side": req.side,
                "orderType": req.type,
                "size": str(size_value),
                "force": req.time_in_force or "gtc",
            }
            if req.type == "limit" and req.limit_price:
                body["price"] = str(req.limit_price)
            data = await self._request("POST", "/api/v2/spot/trade/place-order", body)

        return OrderResponse(
            broker_id=data["orderId"],
            symbol=req.symbol,
            side=req.side,
            quantity=req.quantity,
            type=req.type,
            status="new",
            raw=data,
        )

    async def get_order(self, broker_id: str) -> OrderResponse:
        path = (
            f"/api/v2/mix/order/detail?orderId={broker_id}&productType=USDT-FUTURES"
            if self._simulated
            else f"/api/v2/spot/trade/orderInfo?orderId={broker_id}"
        )
        data = await self._request("GET", path)
        if not data or len(data) == 0:
            raise RuntimeError(f"Order {broker_id} not found")
        return self._to_order_response(data[0] if isinstance(data, list) else data)

    async def cancel_order(self, broker_id: str) -> dict:
        if self._simulated:
            # Mix cancel requires symbol — not available in this interface
            return {
                "success": False,
                "message": "Cancel order in futures mode requires symbol — use close_position instead",
            }
        try:
            await self._request(
                "POST", "/api/v2/spot/trade/cancel-order",
                {"orderId": broker_id},
            )
            return {"success": True, "message": "Order cancelled"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def get_positions(self) -> list[Position]:
        if self._simulated:
            raw = await self._request(
                "GET", "/api/v2/mix/position/all-position?productType=USDT-FUTURES"
            )
            positions = []
            for p in (raw or []):
                qty = float(p.get("total", 0))
                if qty <= 0:
                    continue
                avg_entry = float(p.get("openPriceAvg", 0))
                mark_price = float(p.get("markPrice", 0))
                unrealized_pl = float(p.get("unrealizedPL", 0))
                positions.append(Position(
                    symbol=p["symbol"],
                    quantity=qty,
                    avg_entry_price=avg_entry,
                    current_price=mark_price,
                    market_value=qty * mark_price,
                    unrealized_pl=unrealized_pl,
                    side=p.get("holdSide", "long"),
                ))
            return positions

        # Spot positions
        assets = await self._request("GET", "/api/v2/spot/account/assets")
        non_usdt = [
            a for a in assets
            if a["coin"] != "USDT" and float(a["available"]) + float(a["frozen"]) > 0
        ]

        async def _enrich(a: dict) -> Position:
            symbol = f"{a['coin']}USDT"
            qty = float(a["available"]) + float(a["frozen"])
            price = await self._get_ticker_price(symbol)
            return Position(
                symbol=symbol, quantity=qty,
                avg_entry_price=0, current_price=price,
                market_value=qty * price,
                unrealized_pl=0, side="long",
            )

        return await asyncio.gather(*[_enrich(a) for a in non_usdt])

    async def close_position(
        self, symbol: str, quantity: float | None = None
    ) -> OrderResponse:
        if self._simulated:
            if not quantity:
                raw = await self._request(
                    "GET", "/api/v2/mix/position/all-position?productType=USDT-FUTURES"
                )
                pos = next(
                    (p for p in (raw or [])
                     if p["symbol"] == symbol and p.get("holdSide") == "long"),
                    None,
                )
                if not pos or float(pos.get("available", 0)) <= 0:
                    raise RuntimeError(f"No available long position for {symbol} to close")
                quantity = float(pos["available"])
            return await self.place_order(OrderRequest(
                symbol=symbol, side="sell", quantity=quantity,
                type="market", time_in_force="ioc",
            ))

        if not quantity:
            assets = await self._request("GET", "/api/v2/spot/account/assets")
            coin = symbol.replace("USDT", "")
            asset = next((a for a in assets if a["coin"] == coin), None)
            if not asset or float(asset["available"]) <= 0:
                raise RuntimeError(f"No available {coin} balance to close")
            quantity = float(asset["available"])

        return await self.place_order(OrderRequest(
            symbol=symbol, side="sell", quantity=quantity,
            type="market", time_in_force="ioc",
        ))

    async def get_account(self) -> AccountInfo:
        if self._simulated:
            accounts = await self._request(
                "GET", "/api/v2/mix/account/accounts?productType=USDT-FUTURES"
            )
            usdt_acc = next(
                (a for a in (accounts or []) if a.get("marginCoin") == "USDT"),
                (accounts or [None])[0],
            )
            equity = float(usdt_acc["equity"]) if usdt_acc else 0.0
            available = float(usdt_acc["available"]) if usdt_acc else 0.0
            return AccountInfo(
                equity=equity,
                buying_power=available,
                cash=equity,
                currency="USDT",
            )

        assets = await self._request("GET", "/api/v2/spot/account/assets")

        usdt = next((a for a in assets if a["coin"] == "USDT"), None)
        usdt_available = float(usdt["available"]) if usdt else 0
        usdt_frozen = float(usdt["frozen"]) if usdt else 0
        usdt_total = usdt_available + usdt_frozen

        non_usdt = [
            a for a in assets
            if a["coin"] != "USDT" and float(a["available"]) + float(a["frozen"]) > 0
        ]

        asset_value = 0.0
        if non_usdt:
            prices = await asyncio.gather(*[
                self._get_ticker_price(f"{a['coin']}USDT") for a in non_usdt
            ])
            for a, price in zip(non_usdt, prices):
                qty = float(a["available"]) + float(a["frozen"])
                asset_value += qty * price

        return AccountInfo(
            equity=usdt_total + asset_value,
            buying_power=usdt_available,
            cash=usdt_total,
            currency="USDT",
        )
