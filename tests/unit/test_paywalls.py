"""Unit tests for Paywall endpoints.

Service layer is mocked via dependency override — no DB required.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, status
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.schemas.paywall import PaywallResponse
from app.services.paywall import PaywallService, get_paywall_service

MERCHANT_ID = "merchant-xyz"
HEADERS = {"X-Merchant-Id": MERCHANT_ID}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _paywall(**kwargs) -> PaywallResponse:
    now = datetime.now(timezone.utc)
    return PaywallResponse(
        id=kwargs.get("id", uuid4()),
        merchant_id=kwargs.get("merchant_id", MERCHANT_ID),
        name=kwargs.get("name", "Test Paywall"),
        description=kwargs.get("description", None),
        is_active=kwargs.get("is_active", True),
        paywall_type=kwargs.get("paywall_type", "quick"),
        product_price_id=kwargs.get("product_price_id", None),
        asset=kwargs.get("asset", "USDT"),
        chain=kwargs.get("chain", "ethereum"),
        amount=kwargs.get("amount", "10.00"),
        created_at=kwargs.get("created_at", now),
        updated_at=kwargs.get("updated_at", now),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_service() -> AsyncMock:
    return AsyncMock(spec=PaywallService)


@pytest.fixture(autouse=True)
def override_service(mock_service: AsyncMock):
    app.dependency_overrides[get_paywall_service] = lambda: mock_service
    yield
    app.dependency_overrides.pop(get_paywall_service, None)


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# GET /v1/paywalls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_paywalls_returns_200(client, mock_service):
    mock_service.list_paywalls.return_value = [_paywall(), _paywall()]
    r = await client.get("/v1/paywalls", headers=HEADERS)
    assert r.status_code == 200
    assert len(r.json()) == 2
    mock_service.list_paywalls.assert_called_once_with(MERCHANT_ID)


@pytest.mark.asyncio
async def test_list_paywalls_empty(client, mock_service):
    mock_service.list_paywalls.return_value = []
    r = await client.get("/v1/paywalls", headers=HEADERS)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_paywalls_missing_header_returns_422(client):
    r = await client.get("/v1/paywalls")
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# POST /v1/paywalls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_paywall_returns_201(client, mock_service):
    created = _paywall(name="New Paywall")
    mock_service.create_paywall.return_value = created
    r = await client.post(
        "/v1/paywalls",
        json={"name": "New Paywall", "asset": "USDT", "chain": "ethereum", "amount": "10.00"},
        headers=HEADERS,
    )
    assert r.status_code == 201
    assert r.json()["name"] == "New Paywall"


@pytest.mark.asyncio
async def test_create_paywall_no_products(client, mock_service):
    created = _paywall(name="Empty Paywall")
    mock_service.create_paywall.return_value = created
    r = await client.post(
        "/v1/paywalls",
        json={"name": "Empty Paywall", "asset": "USDT", "chain": "ethereum", "amount": "5.00"},
        headers=HEADERS,
    )
    assert r.status_code == 201
    assert r.json()["name"] == "Empty Paywall"


@pytest.mark.asyncio
async def test_create_paywall_missing_name_returns_422(client, mock_service):
    r = await client.post("/v1/paywalls", json={}, headers=HEADERS)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_paywall_missing_header_returns_422(client):
    r = await client.post("/v1/paywalls", json={"name": "X"})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /v1/paywalls/{paywall_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_paywall_returns_200(client, mock_service):
    wid = uuid4()
    mock_service.get_paywall.return_value = _paywall(id=wid)
    r = await client.get(f"/v1/paywalls/{wid}", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["id"] == str(wid)


@pytest.mark.asyncio
async def test_get_paywall_not_found_returns_404(client, mock_service):
    wid = uuid4()
    mock_service.get_paywall.side_effect = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Paywall not found"
    )
    r = await client.get(f"/v1/paywalls/{wid}", headers=HEADERS)
    assert r.status_code == 404
    assert r.json()["detail"] == "Paywall not found"


@pytest.mark.asyncio
async def test_get_paywall_invalid_uuid_returns_422(client):
    r = await client.get("/v1/paywalls/not-a-uuid", headers=HEADERS)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /v1/paywalls/{paywall_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_paywall_name_returns_200(client, mock_service):
    wid = uuid4()
    mock_service.update_paywall.return_value = _paywall(id=wid, name="Updated")
    r = await client.patch(
        f"/v1/paywalls/{wid}",
        json={"name": "Updated"},
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Updated"


@pytest.mark.asyncio
async def test_update_paywall_asset(client, mock_service):
    wid = uuid4()
    mock_service.update_paywall.return_value = _paywall(id=wid, asset="ETH")
    r = await client.patch(
        f"/v1/paywalls/{wid}",
        json={"asset": "ETH"},
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["asset"] == "ETH"


@pytest.mark.asyncio
async def test_update_paywall_deactivate(client, mock_service):
    wid = uuid4()
    mock_service.update_paywall.return_value = _paywall(id=wid, is_active=False)
    r = await client.patch(
        f"/v1/paywalls/{wid}",
        json={"is_active": False},
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["is_active"] is False


@pytest.mark.asyncio
async def test_update_paywall_not_found_returns_404(client, mock_service):
    wid = uuid4()
    mock_service.update_paywall.side_effect = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Paywall not found"
    )
    r = await client.patch(f"/v1/paywalls/{wid}", json={"name": "x"}, headers=HEADERS)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /v1/paywalls/{paywall_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_paywall_returns_204(client, mock_service):
    wid = uuid4()
    mock_service.delete_paywall.return_value = None
    r = await client.delete(f"/v1/paywalls/{wid}", headers=HEADERS)
    assert r.status_code == 204
    assert r.content == b""


@pytest.mark.asyncio
async def test_delete_paywall_not_found_returns_404(client, mock_service):
    wid = uuid4()
    mock_service.delete_paywall.side_effect = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Paywall not found"
    )
    r = await client.delete(f"/v1/paywalls/{wid}", headers=HEADERS)
    assert r.status_code == 404
