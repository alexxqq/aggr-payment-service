"""Unit tests for WebhookPreparationService — covers payload building and HTTP dispatch."""

import hashlib
import hmac
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import uuid4

import httpx
import pytest

from app.clients.user_service import UserServiceClient
from app.services.webhook import WebhookPreparationService


def _make_intent(
    merchant_id: str = "merchant-webhook",
    chain: str = "ethereum",
    asset: str = "USDC",
    amount: str = "10.00",
    current_status: str = "pending",
) -> AsyncMock:
    m = AsyncMock()
    m.id = uuid4()
    m.merchant_id = merchant_id
    m.chain = chain
    m.asset = asset
    m.amount = amount
    m.status = current_status
    m.created_at = datetime.now(timezone.utc)
    return m


def _make_service(
    webhook_url: str | None = "https://example.com/hook",
    webhook_enabled: bool = True,
    webhook_secret: str | None = "whsec_testsecret",
    config_error: Exception | None = None,
) -> WebhookPreparationService:
    user_client = AsyncMock(spec=UserServiceClient)
    if config_error is not None:
        user_client.get_merchant.side_effect = config_error
    else:
        user_client.get_merchant.return_value = {
            "webhook_url": webhook_url,
            "webhook_enabled": webhook_enabled,
            "webhook_secret": webhook_secret,
        }
    return WebhookPreparationService(user_client)


# ---------------------------------------------------------------------------
# Payload building — existing behaviour preserved
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prepare_returns_payload_when_webhook_enabled():
    service = _make_service()
    intent = _make_intent()

    with patch.object(service, "_dispatch", new_callable=AsyncMock):
        payload = await service.prepare_and_log(intent, "confirmed")

    assert payload is not None
    assert payload["event"] == "payment_intent.status_changed"
    assert payload["payment_intent_id"] == str(intent.id)
    assert payload["merchant_id"] == intent.merchant_id
    assert payload["previous_status"] == intent.status
    assert payload["new_status"] == "confirmed"
    assert payload["chain"] == intent.chain
    assert payload["asset"] == intent.asset
    assert payload["amount"] == str(intent.amount)


@pytest.mark.asyncio
async def test_prepare_returns_none_when_webhook_disabled():
    service = _make_service(webhook_enabled=False)
    intent = _make_intent()

    result = await service.prepare_and_log(intent, "confirmed")
    assert result is None


@pytest.mark.asyncio
async def test_prepare_returns_none_when_webhook_url_missing():
    service = _make_service(webhook_url=None)
    intent = _make_intent()

    result = await service.prepare_and_log(intent, "confirmed")
    assert result is None


@pytest.mark.asyncio
async def test_prepare_returns_none_on_http_error():
    mock_response = MagicMock()
    mock_response.status_code = 500
    error = httpx.HTTPStatusError("error", request=MagicMock(), response=mock_response)
    service = _make_service(config_error=error)
    intent = _make_intent()

    result = await service.prepare_and_log(intent, "confirmed")
    assert result is None


@pytest.mark.asyncio
async def test_prepare_returns_none_on_connect_error():
    service = _make_service(config_error=httpx.ConnectError("refused"))
    intent = _make_intent()

    result = await service.prepare_and_log(intent, "confirmed")
    assert result is None


@pytest.mark.asyncio
async def test_prepare_returns_none_on_timeout():
    service = _make_service(config_error=httpx.TimeoutException("timeout"))
    intent = _make_intent()

    result = await service.prepare_and_log(intent, "confirmed")
    assert result is None


# ---------------------------------------------------------------------------
# HTTP dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_called_when_webhook_enabled():
    service = _make_service()
    intent = _make_intent()

    with patch.object(service, "_dispatch", new_callable=AsyncMock) as mock_dispatch:
        await service.prepare_and_log(intent, "confirmed")

    mock_dispatch.assert_called_once()
    url, payload, secret = mock_dispatch.call_args.args
    assert url == "https://example.com/hook"
    assert payload["event"] == "payment_intent.status_changed"
    assert secret == "whsec_testsecret"


@pytest.mark.asyncio
async def test_dispatch_not_called_when_disabled():
    service = _make_service(webhook_enabled=False)
    intent = _make_intent()

    with patch.object(service, "_dispatch", new_callable=AsyncMock) as mock_dispatch:
        await service.prepare_and_log(intent, "confirmed")

    mock_dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_sends_hmac_signature():
    """HMAC-SHA256 signature must be present in request headers when secret is set."""
    secret = "whsec_testsecret"
    service = _make_service(webhook_secret=secret)
    intent = _make_intent()

    captured_headers: dict = {}

    async def fake_post(url, *, content, headers):
        captured_headers.update(headers)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = fake_post

    with patch("app.services.webhook.httpx.AsyncClient", return_value=mock_client):
        await service.prepare_and_log(intent, "confirmed")

    assert "X-Webhook-Signature" in captured_headers
    sig_header = captured_headers["X-Webhook-Signature"]
    assert sig_header.startswith("sha256=")


@pytest.mark.asyncio
async def test_dispatch_signature_is_correct():
    """Computed HMAC must match what the merchant would compute from the body."""
    secret = "whsec_testsecret"
    service = _make_service(webhook_secret=secret)
    intent = _make_intent()

    captured_body: list[bytes] = []
    captured_sig: list[str] = []

    async def fake_post(url, *, content, headers):
        captured_body.append(content if isinstance(content, bytes) else content.encode())
        captured_sig.append(headers.get("X-Webhook-Signature", ""))
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = fake_post

    with patch("app.services.webhook.httpx.AsyncClient", return_value=mock_client):
        await service.prepare_and_log(intent, "confirmed")

    body_bytes = captured_body[0]
    expected_sig = "sha256=" + hmac.new(
        secret.encode(), body_bytes, hashlib.sha256
    ).hexdigest()
    assert captured_sig[0] == expected_sig


@pytest.mark.asyncio
async def test_dispatch_no_signature_header_when_no_secret():
    service = _make_service(webhook_secret=None)
    intent = _make_intent()

    captured_headers: dict = {}

    async def fake_post(url, *, content, headers):
        captured_headers.update(headers)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = fake_post

    with patch("app.services.webhook.httpx.AsyncClient", return_value=mock_client):
        await service.prepare_and_log(intent, "confirmed")

    assert "X-Webhook-Signature" not in captured_headers


# ---------------------------------------------------------------------------
# Resilience — dispatch errors must not propagate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_failure_does_not_raise():
    """prepare_and_log must return payload even if the HTTP POST fails."""
    service = _make_service()
    intent = _make_intent()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))

    with patch("app.services.webhook.httpx.AsyncClient", return_value=mock_client):
        result = await service.prepare_and_log(intent, "confirmed")

    assert result is not None
    assert result["event"] == "payment_intent.status_changed"


@pytest.mark.asyncio
async def test_dispatch_http_error_does_not_raise():
    """HTTP 500 from merchant server must not propagate."""
    service = _make_service()
    intent = _make_intent()

    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500", request=MagicMock(), response=mock_resp
    )

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("app.services.webhook.httpx.AsyncClient", return_value=mock_client):
        result = await service.prepare_and_log(intent, "confirmed")

    assert result is not None
