"""Unit tests for PaymentIntent and PaymentEvent endpoints.

Service layer is mocked via dependency override — no DB required.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, status
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.schemas.payment_intent import PaymentEventResponse, PaymentIntentResponse
from app.services.payment_intent import PaymentIntentService, get_payment_intent_service

MERCHANT_ID = "merchant-pi"
HEADERS = {"X-Merchant-Id": MERCHANT_ID}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _intent(**kwargs) -> PaymentIntentResponse:
    now = datetime.now(timezone.utc)
    return PaymentIntentResponse(
        id=kwargs.get("id", uuid4()),
        merchant_id=kwargs.get("merchant_id", MERCHANT_ID),
        product_price_id=kwargs.get("product_price_id", None),
        asset=kwargs.get("asset", "USDC"),
        chain=kwargs.get("chain", "ethereum"),
        amount=kwargs.get("amount", "50.00"),
        status=kwargs.get("status", "pending"),
        payer_address=kwargs.get("payer_address", None),
        recipient_address=kwargs.get("recipient_address", None),
        metadata=kwargs.get("metadata", None),
        expires_at=kwargs.get("expires_at", None),
        created_at=kwargs.get("created_at", now),
        updated_at=kwargs.get("updated_at", now),
    )


def _event(payment_intent_id=None, **kwargs) -> PaymentEventResponse:
    now = datetime.now(timezone.utc)
    return PaymentEventResponse(
        id=kwargs.get("id", uuid4()),
        payment_intent_id=payment_intent_id or uuid4(),
        event_type=kwargs.get("event_type", "created"),
        from_status=kwargs.get("from_status", None),
        to_status=kwargs.get("to_status", "pending"),
        data_json=kwargs.get("data_json", None),
        created_at=kwargs.get("created_at", now),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_service() -> AsyncMock:
    return AsyncMock(spec=PaymentIntentService)


@pytest.fixture(autouse=True)
def override_service(mock_service: AsyncMock):
    app.dependency_overrides[get_payment_intent_service] = lambda: mock_service
    yield
    app.dependency_overrides.pop(get_payment_intent_service, None)


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# POST /v1/payment-intents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_intent_returns_201(client, mock_service):
    created = _intent(asset="USDC", chain="ethereum", amount="100.00")
    mock_service.create.return_value = created
    r = await client.post(
        "/v1/payment-intents",
        json={"asset": "USDC", "chain": "ethereum", "amount": "100.00"},
        headers=HEADERS,
    )
    assert r.status_code == 201
    assert r.json()["status"] == "pending"
    assert r.json()["asset"] == "USDC"
    assert r.json()["amount"] == "100.00"
    mock_service.create.assert_called_once()


@pytest.mark.asyncio
async def test_create_intent_with_metadata(client, mock_service):
    meta = {"order_ref": "ORD-001"}
    created = _intent(metadata=meta)
    mock_service.create.return_value = created
    r = await client.post(
        "/v1/payment-intents",
        json={"asset": "ETH", "chain": "ethereum", "amount": "0.1", "metadata": meta},
        headers=HEADERS,
    )
    assert r.status_code == 201
    assert r.json()["metadata"] == meta


@pytest.mark.asyncio
async def test_create_intent_with_product_price_id(client, mock_service):
    price_id = uuid4()
    created = _intent(product_price_id=price_id)
    mock_service.create.return_value = created
    r = await client.post(
        "/v1/payment-intents",
        json={"asset": "USDC", "chain": "polygon", "amount": "5.00",
              "product_price_id": str(price_id)},
        headers=HEADERS,
    )
    assert r.status_code == 201
    assert r.json()["product_price_id"] == str(price_id)


@pytest.mark.asyncio
async def test_create_intent_invalid_amount_returns_422(client, mock_service):
    r = await client.post(
        "/v1/payment-intents",
        json={"asset": "USDC", "chain": "ethereum", "amount": "abc"},
        headers=HEADERS,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_intent_zero_amount_returns_422(client, mock_service):
    r = await client.post(
        "/v1/payment-intents",
        json={"asset": "USDC", "chain": "ethereum", "amount": "0"},
        headers=HEADERS,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_intent_negative_amount_returns_422(client, mock_service):
    r = await client.post(
        "/v1/payment-intents",
        json={"asset": "USDC", "chain": "ethereum", "amount": "-10"},
        headers=HEADERS,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_intent_missing_required_fields_returns_422(client, mock_service):
    r = await client.post(
        "/v1/payment-intents",
        json={"asset": "USDC"},
        headers=HEADERS,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_intent_missing_header_returns_422(client):
    r = await client.post(
        "/v1/payment-intents",
        json={"asset": "USDC", "chain": "ethereum", "amount": "10.00"},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /v1/payment-intents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_intents_returns_200(client, mock_service):
    mock_service.list_intents.return_value = [_intent(), _intent()]
    r = await client.get("/v1/payment-intents", headers=HEADERS)
    assert r.status_code == 200
    assert len(r.json()) == 2
    mock_service.list_intents.assert_called_once_with(MERCHANT_ID, None)


@pytest.mark.asyncio
async def test_list_intents_with_status_filter(client, mock_service):
    mock_service.list_intents.return_value = [_intent(status="completed")]
    r = await client.get("/v1/payment-intents?status=completed", headers=HEADERS)
    assert r.status_code == 200
    mock_service.list_intents.assert_called_once_with(MERCHANT_ID, "completed")


@pytest.mark.asyncio
async def test_list_intents_empty(client, mock_service):
    mock_service.list_intents.return_value = []
    r = await client.get("/v1/payment-intents", headers=HEADERS)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_intents_missing_header_returns_422(client):
    r = await client.get("/v1/payment-intents")
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /v1/payment-intents/{payment_intent_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_intent_returns_200(client, mock_service):
    iid = uuid4()
    mock_service.get.return_value = _intent(id=iid)
    r = await client.get(f"/v1/payment-intents/{iid}", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["id"] == str(iid)


@pytest.mark.asyncio
async def test_get_intent_not_found_returns_404(client, mock_service):
    iid = uuid4()
    mock_service.get.side_effect = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Payment intent not found"
    )
    r = await client.get(f"/v1/payment-intents/{iid}", headers=HEADERS)
    assert r.status_code == 404
    assert r.json()["detail"] == "Payment intent not found"


@pytest.mark.asyncio
async def test_get_intent_invalid_uuid_returns_422(client):
    r = await client.get("/v1/payment-intents/not-a-uuid", headers=HEADERS)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /v1/payment-intents/{payment_intent_id}/events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_events_returns_200(client, mock_service):
    iid = uuid4()
    events = [
        _event(payment_intent_id=iid, event_type="created", to_status="pending"),
    ]
    mock_service.list_events.return_value = events
    r = await client.get(f"/v1/payment-intents/{iid}/events", headers=HEADERS)
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["event_type"] == "created"
    assert r.json()[0]["to_status"] == "pending"


@pytest.mark.asyncio
async def test_list_events_empty(client, mock_service):
    iid = uuid4()
    mock_service.list_events.return_value = []
    r = await client.get(f"/v1/payment-intents/{iid}/events", headers=HEADERS)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_events_intent_not_found_returns_404(client, mock_service):
    iid = uuid4()
    mock_service.list_events.side_effect = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Payment intent not found"
    )
    r = await client.get(f"/v1/payment-intents/{iid}/events", headers=HEADERS)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_list_events_missing_header_returns_422(client):
    iid = uuid4()
    r = await client.get(f"/v1/payment-intents/{iid}/events")
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# POST /v1/payment-intents/{payment_intent_id}/execute
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_intent_returns_200(client, mock_service):
    iid = uuid4()
    confirmed = _intent(id=iid, status="confirmed")
    mock_service.execute.return_value = confirmed
    r = await client.post(f"/v1/payment-intents/{iid}/execute", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["status"] == "confirmed"
    mock_service.execute.assert_called_once_with(iid, MERCHANT_ID)


@pytest.mark.asyncio
async def test_execute_intent_not_pending_returns_422(client, mock_service):
    iid = uuid4()
    mock_service.execute.side_effect = HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="Cannot execute: intent is in status 'confirmed', expected 'pending'",
    )
    r = await client.post(f"/v1/payment-intents/{iid}/execute", headers=HEADERS)
    assert r.status_code == 422
    assert "pending" in r.json()["detail"]


@pytest.mark.asyncio
async def test_execute_intent_not_found_returns_404(client, mock_service):
    iid = uuid4()
    mock_service.execute.side_effect = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Payment intent not found"
    )
    r = await client.post(f"/v1/payment-intents/{iid}/execute", headers=HEADERS)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_execute_intent_missing_header_returns_422(client):
    iid = uuid4()
    r = await client.post(f"/v1/payment-intents/{iid}/execute")
    assert r.status_code == 422
