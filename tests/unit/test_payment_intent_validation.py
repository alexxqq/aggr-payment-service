"""Unit tests for PaymentIntent merchant validation via User Service.

Tests are written at the service level so they exercise the actual
_validate_merchant logic without mocking the whole service.
The DB session and UserServiceClient are both mocked.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException

from app.clients.user_service import MerchantCapabilities, UserServiceClient
from app.schemas.payment_intent import PaymentIntentCreate
from app.services.payment_intent import PaymentIntentService

MERCHANT_ID = "merchant-validation-test"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _capabilities(**kwargs) -> MerchantCapabilities:
    return MerchantCapabilities(
        merchant_id=kwargs.get("merchant_id", MERCHANT_ID),
        is_active=kwargs.get("is_active", True),
        allowed_chains=kwargs.get("allowed_chains", ["ethereum", "polygon"]),
        allowed_assets=kwargs.get("allowed_assets", ["USDC", "ETH"]),
        default_chain=kwargs.get("default_chain", "ethereum"),
    )


def _intent_mock() -> MagicMock:
    now = datetime.now(timezone.utc)
    m = MagicMock()
    m.id = uuid4()
    m.merchant_id = MERCHANT_ID
    m.product_price_id = None
    m.asset = "USDC"
    m.chain = "ethereum"
    m.amount = "10.00"
    m.status = "pending"
    m.payer_address = None
    m.recipient_address = None
    m.metadata_json = None
    m.expires_at = None
    m.created_at = now
    m.updated_at = now
    return m


def _make_service(
    caps: MerchantCapabilities | None = None,
    caps_error: Exception | None = None,
) -> PaymentIntentService:
    """Build a PaymentIntentService with mocked DB and mocked UserServiceClient."""
    db = AsyncMock()
    user_client = AsyncMock(spec=UserServiceClient)

    if caps_error is not None:
        user_client.get_merchant_capabilities.side_effect = caps_error
    else:
        user_client.get_merchant_capabilities.return_value = caps or _capabilities()

    service = PaymentIntentService(db=db, user_client=user_client)
    service.repo = AsyncMock()
    service.repo.create = AsyncMock(return_value=_intent_mock())
    service.event_repo = AsyncMock()
    service.event_repo.create = AsyncMock(return_value=MagicMock())
    return service


VALID_DATA = PaymentIntentCreate(asset="USDC", chain="ethereum", amount="10.00")


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_succeeds_with_active_merchant():
    service = _make_service()
    result = await service.create(MERCHANT_ID, VALID_DATA)
    assert result.status == "pending"
    assert result.asset == "USDC"


@pytest.mark.asyncio
async def test_create_calls_user_service_with_merchant_id():
    service = _make_service()
    await service.create(MERCHANT_ID, VALID_DATA)
    service.user_client.get_merchant_capabilities.assert_called_once_with(MERCHANT_ID)


@pytest.mark.asyncio
async def test_create_stores_intent_and_event_when_valid():
    service = _make_service()
    await service.create(MERCHANT_ID, VALID_DATA)
    service.repo.create.assert_called_once()
    service.event_repo.create.assert_called_once()
    call_kwargs = service.event_repo.create.call_args.kwargs
    assert call_kwargs["event_type"] == "created"
    assert call_kwargs["to_status"] == "pending"


# ---------------------------------------------------------------------------
# Merchant inactive
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_fails_if_merchant_not_active():
    service = _make_service(caps=_capabilities(is_active=False))
    with pytest.raises(HTTPException) as exc_info:
        await service.create(MERCHANT_ID, VALID_DATA)
    assert exc_info.value.status_code == 422
    assert "not active" in exc_info.value.detail


@pytest.mark.asyncio
async def test_create_does_not_persist_if_merchant_inactive():
    service = _make_service(caps=_capabilities(is_active=False))
    with pytest.raises(HTTPException):
        await service.create(MERCHANT_ID, VALID_DATA)
    service.repo.create.assert_not_called()
    service.event_repo.create.assert_not_called()


# ---------------------------------------------------------------------------
# Chain not allowed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_fails_if_chain_not_allowed():
    service = _make_service(caps=_capabilities(allowed_chains=["polygon"]))
    data = PaymentIntentCreate(asset="USDC", chain="ethereum", amount="10.00")
    with pytest.raises(HTTPException) as exc_info:
        await service.create(MERCHANT_ID, data)
    assert exc_info.value.status_code == 422
    assert "chain" in exc_info.value.detail.lower()
    assert "ethereum" in exc_info.value.detail


@pytest.mark.asyncio
async def test_create_succeeds_with_allowed_chain():
    service = _make_service(caps=_capabilities(allowed_chains=["polygon"]))
    data = PaymentIntentCreate(asset="USDC", chain="polygon", amount="10.00")
    result = await service.create(MERCHANT_ID, data)
    assert result is not None


# ---------------------------------------------------------------------------
# Asset not allowed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_fails_if_asset_not_allowed():
    service = _make_service(caps=_capabilities(allowed_assets=["ETH"]))
    data = PaymentIntentCreate(asset="USDC", chain="ethereum", amount="10.00")
    with pytest.raises(HTTPException) as exc_info:
        await service.create(MERCHANT_ID, data)
    assert exc_info.value.status_code == 422
    assert "asset" in exc_info.value.detail.lower()
    assert "USDC" in exc_info.value.detail


@pytest.mark.asyncio
async def test_create_succeeds_with_allowed_asset():
    service = _make_service(caps=_capabilities(allowed_assets=["ETH"]))
    data = PaymentIntentCreate(asset="ETH", chain="ethereum", amount="0.05")
    result = await service.create(MERCHANT_ID, data)
    assert result is not None


# ---------------------------------------------------------------------------
# User Service error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_fails_with_422_if_merchant_not_found_in_user_service():
    mock_response = MagicMock()
    mock_response.status_code = 404
    error = httpx.HTTPStatusError(
        "Not Found", request=MagicMock(), response=mock_response
    )
    service = _make_service(caps_error=error)
    with pytest.raises(HTTPException) as exc_info:
        await service.create(MERCHANT_ID, VALID_DATA)
    assert exc_info.value.status_code == 422
    assert "not found" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_create_fails_with_503_if_user_service_http_error():
    mock_response = MagicMock()
    mock_response.status_code = 500
    error = httpx.HTTPStatusError(
        "Internal Server Error", request=MagicMock(), response=mock_response
    )
    service = _make_service(caps_error=error)
    with pytest.raises(HTTPException) as exc_info:
        await service.create(MERCHANT_ID, VALID_DATA)
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_create_fails_with_503_if_user_service_unreachable():
    service = _make_service(
        caps_error=httpx.ConnectError("Connection refused")
    )
    with pytest.raises(HTTPException) as exc_info:
        await service.create(MERCHANT_ID, VALID_DATA)
    assert exc_info.value.status_code == 503
    assert "unavailable" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_create_fails_with_503_if_user_service_timeout():
    service = _make_service(
        caps_error=httpx.TimeoutException("Request timed out")
    )
    with pytest.raises(HTTPException) as exc_info:
        await service.create(MERCHANT_ID, VALID_DATA)
    assert exc_info.value.status_code == 503
    assert "unavailable" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_create_does_not_persist_if_user_service_unreachable():
    service = _make_service(
        caps_error=httpx.ConnectError("Connection refused")
    )
    with pytest.raises(HTTPException):
        await service.create(MERCHANT_ID, VALID_DATA)
    service.repo.create.assert_not_called()
    service.event_repo.create.assert_not_called()
