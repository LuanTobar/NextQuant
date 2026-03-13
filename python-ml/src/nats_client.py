import json
import nats
import structlog
from nats.aio.client import Client

logger = structlog.get_logger()


def _json_default(obj):
    """Convert numpy scalar types to Python natives for JSON serialization."""
    import numpy as np
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.bool_):
        return bool(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


class NATSClient:
    def __init__(self, url: str):
        self.url = url
        self.nc: Client | None = None

    async def connect(self):
        self.nc = await nats.connect(self.url)
        logger.info("Connected to NATS", url=self.url)

    async def subscribe(self, subject: str, callback):
        if not self.nc:
            raise RuntimeError("Not connected to NATS")
        await self.nc.subscribe(subject, cb=callback)
        logger.info("Subscribed to subject", subject=subject)

    async def publish(self, subject: str, data: dict):
        if not self.nc:
            raise RuntimeError("Not connected to NATS")
        payload = json.dumps(data, default=_json_default).encode()
        await self.nc.publish(subject, payload)

    async def close(self):
        if self.nc:
            await self.nc.drain()
            logger.info("NATS connection closed")
