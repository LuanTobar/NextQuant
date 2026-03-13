"""
Alerter — fire-and-forget webhook notifications for critical trading events.

Compatible with Discord, Slack, and any HTTP webhook that accepts JSON POST.
Configure ALERT_WEBHOOK_URL in .env; leave empty to disable silently.
"""

import httpx
import structlog

logger = structlog.get_logger()


class Alerter:
    def __init__(self, webhook_url: str | None):
        self._url = webhook_url or ""

    @property
    def enabled(self) -> bool:
        return bool(self._url)

    async def send(
        self,
        client: httpx.AsyncClient,
        level: str,
        title: str,
        body: str,
        user_id: str = "",
    ) -> None:
        """Send alert via webhook. Never raises — failures are logged and swallowed.

        Args:
            client:  Shared httpx.AsyncClient (caller manages lifecycle).
            level:   "CRITICAL" | "WARNING" | "INFO"
            title:   Short one-line summary.
            body:    Details (prices, PnL, reasons, etc.).
            user_id: Optional user context appended to the message.
        """
        if not self._url:
            return

        text = f"**[{level}] {title}**"
        if user_id:
            text += f" — user `{user_id}`"
        text += f"\n{body}"

        try:
            await client.post(self._url, json={"content": text}, timeout=5.0)
            logger.debug("Alert sent", level=level, title=title)
        except Exception as e:
            logger.warning("Alert send failed", level=level, title=title, error=str(e))
