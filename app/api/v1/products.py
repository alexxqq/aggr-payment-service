"""Product and ProductPrice endpoints."""

import uuid

from fastapi import APIRouter, Depends, Header, status

from app.schemas.product import (
    ProductCreate,
    ProductPriceCreate,
    ProductPriceResponse,
    ProductResponse,
    ProductUpdate,
)
from app.services.product import ProductService, get_product_service

router = APIRouter(prefix="/products", tags=["products"])


def _merchant_id(x_merchant_id: str = Header(...)) -> str:
    """Extract merchant identity from gateway-injected header."""
    return x_merchant_id


@router.get("", response_model=list[ProductResponse])
async def list_products(
    merchant_id: str = Depends(_merchant_id),
    service: ProductService = Depends(get_product_service),
) -> list[ProductResponse]:
    return await service.list_products(merchant_id)


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    body: ProductCreate,
    merchant_id: str = Depends(_merchant_id),
    service: ProductService = Depends(get_product_service),
) -> ProductResponse:
    return await service.create_product(merchant_id, body)


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: uuid.UUID,
    merchant_id: str = Depends(_merchant_id),
    service: ProductService = Depends(get_product_service),
) -> ProductResponse:
    return await service.get_product(product_id, merchant_id)


@router.patch("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: uuid.UUID,
    body: ProductUpdate,
    merchant_id: str = Depends(_merchant_id),
    service: ProductService = Depends(get_product_service),
) -> ProductResponse:
    return await service.update_product(product_id, merchant_id, body)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: uuid.UUID,
    merchant_id: str = Depends(_merchant_id),
    service: ProductService = Depends(get_product_service),
) -> None:
    await service.delete_product(product_id, merchant_id)


@router.get("/{product_id}/prices", response_model=list[ProductPriceResponse])
async def list_product_prices(
    product_id: uuid.UUID,
    merchant_id: str = Depends(_merchant_id),
    service: ProductService = Depends(get_product_service),
) -> list[ProductPriceResponse]:
    return await service.list_prices(product_id, merchant_id)


@router.post(
    "/{product_id}/prices",
    response_model=ProductPriceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_product_price(
    product_id: uuid.UUID,
    body: ProductPriceCreate,
    merchant_id: str = Depends(_merchant_id),
    service: ProductService = Depends(get_product_service),
) -> ProductPriceResponse:
    return await service.create_price(product_id, merchant_id, body)
