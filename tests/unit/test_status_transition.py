"""Unit tests for PaymentIntentService.transition_status_internal."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.clients.user_service import MerchantCapabilities, UserServiceClient
from app.services.payment_intent import ALLOWED_TRANSITIONS, PaymentIntentService

MERCHANT_ID = "merchant-transition-test"


def _caps() -> MerchantCapabilities:
    return MerchantCapabilities(
        merchant_id=MERCHANT_ID,
        is_active=True,
        allowed_chains=["ethereum"],
        allowed_assets=["USDC"],
        default_chain="ethereum",
    )


def _make_intent(status: str = "pending") -> MagicMock:
    now = datetime.now(timezone.utc)
    m = MagicMock()
    m.id = uuid4()
    m.merchant_id = MERCHANT_ID
    m.product_price_id = None
    m.asset = "USDC"
    m.chain = "ethereum"
    m.amount = "10.00"
    m.status = status
    m.payer_address = None
    m.recipient_address = None
    m.metadata_json = None
    m.expires_at = None
    m.created_at = now
    m.updated_at = now
    return m


def _make_service(intent: MagicMock | None = None) -> PaymentIntentService:
    db = AsyncMock()
    user_client = AsyncMock(spec=UserServiceClient)
    user_client.get_merchant_capabilities.return_value = _caps()
    # Webhook prep should be a no-op in transition tests
    user_client.get_merchant.side_effect = Exception("User Service unavailable")

    service = PaymentIntentService(db=db, user_client=user_client)
    service.repo = AsyncMock()
    service.event_repo = AsyncMock()

    if intent is not None:
        service.repo.get.return_value = intent
        updated = MagicMock()
        updated.id = intent.id
        updated.merchant_id = intent.merchant_id
        updated.product_price_id = None
        updated.asset = intent.asset
        updated.chain = intent.chain
        updated.amount = intent.amount
        updated.status = "updated"  # will be overridden per test
        updated.payer_address = None
        updated.recipient_address = None
        updated.metadata_json = None
        updated.expires_at = None
        updated.created_at = intent.created_at
        updated.updated_at = intent.updated_at
        service.repo.update_status = AsyncMock(return_value=updated)
    else:
        service.repo.get.return_value = None

    service.event_repo.create = AsyncMock(return_value=MagicMock())
    return service


# ---------------------------------------------------------------------------
# ALLOWED_TRANSITIONS constant
# ---------------------------------------------------------------------------


def test_allowed_transitions_pending():
    assert ALLOWED_TRANSITIONS["pending"] == {"confirmed", "failed", "expired"}


def test_allowed_transitions_confirmed():
    assert ALLOWED_TRANSITIONS["confirmed"] == {"completed", "failed", "expired"}


def test_allowed_transitions_terminal_states():
    for terminal in ("completed", "failed", "expired"):
        assert ALLOWED_TRANSITIONS[terminal] == set()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transition_pending_to_confirmed():
    intent = _make_intent(status="pending")
    service = _make_service(intent)
    service.repo.update_status.return_value.status = "confirmed"
    result = await service.transition_status_internal(intent.id, "confirmed")
    service.repo.update_status.assert_called_once_with(intent, "confirmed")
    assert result is not None


@pytest.mark.asyncio
async def test_transition_appends_status_changed_event():
    intent = _make_intent(status="pending")
    service = _make_service(intent)
    await service.transition_status_internal(intent.id, "confirmed")
    call_kwargs = service.event_repo.create.call_args.kwargs
    assert call_kwargs["event_type"] == "status_changed"
    assert call_kwargs["from_status"] == "pending"
    assert call_kwargs["to_status"] == "confirmed"


@pytest.mark.asyncio
async def test_transition_stores_data_json():
    intent = _make_intent(status="pending")
    service = _make_service(intent)
    await service.transition_status_internal(intent.id, "confirmed", data={"tx": "0xabc"})
    call_kwargs = service.event_repo.create.call_args.kwargs
    assert '"tx"' in call_kwargs["data_json"]
    assert "0xabc" in call_kwargs["data_json"]


@pytest.mark.asyncio
async def test_transition_no_data_json_when_data_is_none():
    intent = _make_intent(status="pending")
    service = _make_service(intent)
    await service.transition_status_internal(intent.id, "confirmed", data=None)
    call_kwargs = service.event_repo.create.call_args.kwargs
    assert call_kwargs["data_json"] is None


# ---------------------------------------------------------------------------
# Invalid transitions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_transition_raises_422():
    intent = _make_intent(status="pending")
    service = _make_service(intent)
    with pytest.raises(HTTPException) as exc_info:
        await service.transition_status_internal(intent.id, "completed")
    assert exc_info.value.status_code == 422
    assert "pending" in exc_info.value.detail
    assert "completed" in exc_info.value.detail


@pytest.mark.asyncio
async def test_terminal_state_rejects_any_transition():
    for terminal in ("completed", "failed", "expired"):
        intent = _make_intent(status=terminal)
        service = _make_service(intent)
        with pytest.raises(HTTPException) as exc_info:
            await service.transition_status_internal(intent.id, "pending")
        assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# Intent not found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transition_returns_404_if_intent_not_found():
    service = _make_service(intent=None)
    with pytest.raises(HTTPException) as exc_info:
        await service.transition_status_internal(uuid4(), "confirmed")
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Webhook error does not fail the transition
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transition_succeeds_even_if_webhook_prep_raises():
    intent = _make_intent(status="pending")
    service = _make_service(intent)
    # Webhook prep will fail (user_client.get_merchant raises), but transition succeeds
    result = await service.transition_status_internal(intent.id, "confirmed")
    assert result is not None
    service.repo.update_status.assert_called_once()
    service.event_repo.create.assert_called_once()
