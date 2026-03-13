from .base import BrokerClient, OrderRequest, OrderResponse, Position, AccountInfo
from .alpaca import AlpacaClient
from .bitget import BitgetClient


def create_broker_client(
    broker_type: str, api_key: str, api_secret: str, extra: dict
) -> BrokerClient:
    if broker_type == "ALPACA":
        return AlpacaClient(api_key, api_secret, extra.get("environment", "paper"))
    elif broker_type == "BITGET":
        return BitgetClient(
            api_key, api_secret,
            extra.get("passphrase", ""),
            simulated=bool(extra.get("simulated", False)),
        )
    raise ValueError(f"Unsupported broker: {broker_type}")
