"""Unit tests for Product and ProductPrice endpoints.

Service layer is mocked via dependency override — no DB required.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, status
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.schemas.product import ProductPriceResponse, ProductResponse
from app.services.product import ProductService, get_product_service

MERCHANT_ID = "merchant-abc"
HEADERS = {"X-Merchant-Id": MERCHANT_ID}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _product(**kwargs) -> ProductResponse:
    now = datetime.now(timezone.utc)
    return ProductResponse(
        id=kwargs.get("id", uuid4()),
        merchant_id=kwargs.get("merchant_id", MERCHANT_ID),
        name=kwargs.get("name", "Test Product"),
        description=kwargs.get("description", None),
        is_active=kwargs.get("is_active", True),
        created_at=kwargs.get("created_at", now),
        updated_at=kwargs.get("updated_at", now),
    )


def _price(product_id=None, **kwargs) -> ProductPriceResponse:
    now = datetime.now(timezone.utc)
    return ProductPriceResponse(
        id=kwargs.get("id", uuid4()),
        product_id=product_id or uuid4(),
        asset=kwargs.get("asset", "USDC"),
        chain=kwargs.get("chain", "ethereum"),
        amount=kwargs.get("amount", "10.00"),
        is_active=kwargs.get("is_active", True),
        created_at=kwargs.get("created_at", now),
        updated_at=kwargs.get("updated_at", now),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_service() -> AsyncMock:
    return AsyncMock(spec=ProductService)


@pytest.fixture(autouse=True)
def override_service(mock_service: AsyncMock):
    app.dependency_overrides[get_product_service] = lambda: mock_service
    yield
    app.dependency_overrides.pop(get_product_service, None)


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# GET /v1/products
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_products_returns_200(client, mock_service):
    mock_service.list_products.return_value = [_product(), _product()]
    r = await client.get("/v1/products", headers=HEADERS)
    assert r.status_code == 200
    assert len(r.json()) == 2
    mock_service.list_products.assert_called_once_with(MERCHANT_ID)


@pytest.mark.asyncio
async def test_list_products_empty(client, mock_service):
    mock_service.list_products.return_value = []
    r = await client.get("/v1/products", headers=HEADERS)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_products_missing_header_returns_422(client):
    r = await client.get("/v1/products")
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# POST /v1/products
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_product_returns_201(client, mock_service):
    created = _product(name="New Product", description="desc")
    mock_service.create_product.return_value = created
    r = await client.post(
        "/v1/products",
        json={"name": "New Product", "description": "desc"},
        headers=HEADERS,
    )
    assert r.status_code == 201
    assert r.json()["name"] == "New Product"
    assert r.json()["merchant_id"] == MERCHANT_ID


@pytest.mark.asyncio
async def test_create_product_missing_name_returns_422(client, mock_service):
    r = await client.post("/v1/products", json={}, headers=HEADERS)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_product_missing_header_returns_422(client):
    r = await client.post("/v1/products", json={"name": "X"})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /v1/products/{product_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_product_returns_200(client, mock_service):
    pid = uuid4()
    mock_service.get_product.return_value = _product(id=pid)
    r = await client.get(f"/v1/products/{pid}", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["id"] == str(pid)


@pytest.mark.asyncio
async def test_get_product_not_found_returns_404(client, mock_service):
    pid = uuid4()
    mock_service.get_product.side_effect = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
    )
    r = await client.get(f"/v1/products/{pid}", headers=HEADERS)
    assert r.status_code == 404
    assert r.json()["detail"] == "Product not found"


@pytest.mark.asyncio
async def test_get_product_invalid_uuid_returns_422(client, mock_service):
    r = await client.get("/v1/products/not-a-uuid", headers=HEADERS)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /v1/products/{product_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_product_returns_200(client, mock_service):
    pid = uuid4()
    mock_service.update_product.return_value = _product(id=pid, name="Updated")
    r = await client.patch(
        f"/v1/products/{pid}",
        json={"name": "Updated"},
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Updated"


@pytest.mark.asyncio
async def test_update_product_deactivate(client, mock_service):
    pid = uuid4()
    mock_service.update_product.return_value = _product(id=pid, is_active=False)
    r = await client.patch(
        f"/v1/products/{pid}",
        json={"is_active": False},
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["is_active"] is False


@pytest.mark.asyncio
async def test_update_product_not_found_returns_404(client, mock_service):
    pid = uuid4()
    mock_service.update_product.side_effect = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
    )
    r = await client.patch(f"/v1/products/{pid}", json={"name": "x"}, headers=HEADERS)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /v1/products/{product_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_product_returns_204(client, mock_service):
    pid = uuid4()
    mock_service.delete_product.return_value = None
    r = await client.delete(f"/v1/products/{pid}", headers=HEADERS)
    assert r.status_code == 204
    assert r.content == b""


@pytest.mark.asyncio
async def test_delete_product_not_found_returns_404(client, mock_service):
    pid = uuid4()
    mock_service.delete_product.side_effect = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
    )
    r = await client.delete(f"/v1/products/{pid}", headers=HEADERS)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /v1/products/{product_id}/prices
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_prices_returns_200(client, mock_service):
    pid = uuid4()
    mock_service.list_prices.return_value = [_price(product_id=pid), _price(product_id=pid)]
    r = await client.get(f"/v1/products/{pid}/prices", headers=HEADERS)
    assert r.status_code == 200
    assert len(r.json()) == 2


@pytest.mark.asyncio
async def test_list_prices_product_not_found_returns_404(client, mock_service):
    pid = uuid4()
    mock_service.list_prices.side_effect = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
    )
    r = await client.get(f"/v1/products/{pid}/prices", headers=HEADERS)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /v1/products/{product_id}/prices
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_price_returns_201(client, mock_service):
    pid = uuid4()
    mock_service.create_price.return_value = _price(product_id=pid, amount="25.00")
    r = await client.post(
        f"/v1/products/{pid}/prices",
        json={"asset": "USDC", "chain": "ethereum", "amount": "25.00"},
        headers=HEADERS,
    )
    assert r.status_code == 201
    assert r.json()["amount"] == "25.00"
    assert r.json()["asset"] == "USDC"


@pytest.mark.asyncio
async def test_create_price_invalid_amount_returns_422(client, mock_service):
    pid = uuid4()
    r = await client.post(
        f"/v1/products/{pid}/prices",
        json={"asset": "USDC", "chain": "ethereum", "amount": "not-a-number"},
        headers=HEADERS,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_price_zero_amount_returns_422(client, mock_service):
    pid = uuid4()
    r = await client.post(
        f"/v1/products/{pid}/prices",
        json={"asset": "USDC", "chain": "ethereum", "amount": "0"},
        headers=HEADERS,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_price_negative_amount_returns_422(client, mock_service):
    pid = uuid4()
    r = await client.post(
        f"/v1/products/{pid}/prices",
        json={"asset": "USDC", "chain": "ethereum", "amount": "-1.00"},
        headers=HEADERS,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_price_missing_fields_returns_422(client, mock_service):
    pid = uuid4()
    r = await client.post(
        f"/v1/products/{pid}/prices",
        json={"asset": "USDC"},
        headers=HEADERS,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_price_product_not_found_returns_404(client, mock_service):
    pid = uuid4()
    mock_service.create_price.side_effect = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
    )
    r = await client.post(
        f"/v1/products/{pid}/prices",
        json={"asset": "USDC", "chain": "ethereum", "amount": "5.00"},
        headers=HEADERS,
    )
    assert r.status_code == 404
