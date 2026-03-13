import json
import nats
import structlog
from nats.aio.client import Client

logger = structlog.get_logger()


class NATSClient:
    def __init__(self, url: str):
        self.url = url
        self.nc: Client | None = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self):
        self.nc = await nats.connect(
            self.url,
            reconnect_time_wait=2,       # 2s between reconnect attempts
            max_reconnect_attempts=-1,   # retry forever
            disconnected_cb=self._on_disconnect,
            reconnected_cb=self._on_reconnect,
            error_cb=self._on_error,
        )
        self._connected = True
        logger.info("Connected to NATS", url=self.url)

    async def _on_disconnect(self):
        self._connected = False
        logger.warning("NATS disconnected — buffering outbound messages")

    async def _on_reconnect(self):
        self._connected = True
        logger.info("NATS reconnected", url=self.url)

    async def _on_error(self, e):
        logger.error("NATS error", error=str(e))

    async def subscribe(self, subject: str, callback):
        if not self.nc:
            raise RuntimeError("Not connected to NATS")
        await self.nc.subscribe(subject, cb=callback)
        logger.info("Subscribed to subject", subject=subject)

    async def publish(self, subject: str, data: dict):
        if not self.nc:
            raise RuntimeError("Not connected to NATS")
        payload = json.dumps(data).encode()
        await self.nc.publish(subject, payload)

    async def close(self):
        if self.nc:
            await self.nc.drain()
            self._connected = False
            logger.info("NATS connection closed")
