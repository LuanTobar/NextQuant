"""
Tests for Alerter — webhook notification module.

Run: python -m pytest tests/test_alerter.py -v
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.alerter import Alerter


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_client(raise_error: Exception | None = None):
    client = MagicMock()
    if raise_error:
        client.post = AsyncMock(side_effect=raise_error)
    else:
        resp = MagicMock()
        resp.status_code = 204
        client.post = AsyncMock(return_value=resp)
    return client


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── TestEnabled ───────────────────────────────────────────────────────────────

class TestEnabled:
    def test_empty_url_not_enabled(self):
        assert Alerter("").enabled is False

    def test_none_url_not_enabled(self):
        assert Alerter(None).enabled is False

    def test_valid_url_enabled(self):
        assert Alerter("https://example.com/webhook").enabled is True


# ── TestSendDisabled ─────────────────────────────────────────────────────────

class TestSendDisabled:
    def test_no_post_when_url_empty(self):
        alerter = Alerter("")
        client = _mock_client()
        _run(alerter.send(client, "CRITICAL", "title", "body"))
        client.post.assert_not_called()

    def test_no_post_when_url_none(self):
        alerter = Alerter(None)
        client = _mock_client()
        _run(alerter.send(client, "WARNING", "title", "body"))
        client.post.assert_not_called()

    def test_send_does_not_raise_when_disabled(self):
        alerter = Alerter("")
        client = _mock_client(raise_error=RuntimeError("should not be called"))
        # Must not raise
        _run(alerter.send(client, "CRITICAL", "title", "body"))


# ── TestSendEnabled ───────────────────────────────────────────────────────────

class TestSendEnabled:
    def test_posts_to_webhook_url(self):
        url = "https://discord.com/api/webhooks/test"
        alerter = Alerter(url)
        client = _mock_client()
        _run(alerter.send(client, "CRITICAL", "Daily loss limit hit", "$500 loss"))
        client.post.assert_called_once()
        call_url = client.post.call_args[0][0]
        assert call_url == url

    def test_payload_contains_level(self):
        alerter = Alerter("https://example.com/hook")
        client = _mock_client()
        _run(alerter.send(client, "CRITICAL", "Test title", "Test body"))
        payload = client.post.call_args[1]["json"]
        assert "CRITICAL" in payload["content"]

    def test_payload_contains_title(self):
        alerter = Alerter("https://example.com/hook")
        client = _mock_client()
        _run(alerter.send(client, "WARNING", "Max drawdown reached", "15% drawdown"))
        payload = client.post.call_args[1]["json"]
        assert "Max drawdown reached" in payload["content"]

    def test_payload_contains_body(self):
        alerter = Alerter("https://example.com/hook")
        client = _mock_client()
        _run(alerter.send(client, "INFO", "title", "15% drawdown on AAPL"))
        payload = client.post.call_args[1]["json"]
        assert "15% drawdown on AAPL" in payload["content"]

    def test_payload_contains_user_id_when_provided(self):
        alerter = Alerter("https://example.com/hook")
        client = _mock_client()
        _run(alerter.send(client, "CRITICAL", "title", "body", user_id="user123"))
        payload = client.post.call_args[1]["json"]
        assert "user123" in payload["content"]

    def test_payload_excludes_user_id_when_empty(self):
        alerter = Alerter("https://example.com/hook")
        client = _mock_client()
        _run(alerter.send(client, "CRITICAL", "title", "body", user_id=""))
        payload = client.post.call_args[1]["json"]
        # Should not contain "user `" pattern
        assert "user `" not in payload["content"]

    def test_timeout_passed_to_post(self):
        alerter = Alerter("https://example.com/hook")
        client = _mock_client()
        _run(alerter.send(client, "INFO", "title", "body"))
        call_kwargs = client.post.call_args[1]
        assert call_kwargs.get("timeout") == 5.0


# ── TestSendResiliency ────────────────────────────────────────────────────────

class TestSendResiliency:
    def test_network_error_does_not_raise(self):
        alerter = Alerter("https://example.com/hook")
        client = _mock_client(raise_error=ConnectionError("network down"))
        # Must not raise
        _run(alerter.send(client, "CRITICAL", "title", "body"))

    def test_timeout_error_does_not_raise(self):
        import httpx
        alerter = Alerter("https://example.com/hook")
        client = _mock_client(raise_error=httpx.TimeoutException("timeout"))
        _run(alerter.send(client, "WARNING", "title", "body"))

    def test_generic_exception_does_not_raise(self):
        alerter = Alerter("https://example.com/hook")
        client = _mock_client(raise_error=Exception("unexpected"))
        _run(alerter.send(client, "INFO", "title", "body"))

    def test_subsequent_send_works_after_failure(self):
        alerter = Alerter("https://example.com/hook")
        failing_client = _mock_client(raise_error=ConnectionError("fail"))
        ok_client = _mock_client()
        _run(alerter.send(failing_client, "CRITICAL", "title", "body"))
        _run(alerter.send(ok_client, "INFO", "recovered", "all good"))
        ok_client.post.assert_called_once()
