"""Service layer for Product and ProductPrice."""

import uuid

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.product import Product
from app.repositories.product import ProductPriceRepository, ProductRepository
from app.schemas.product import (
    ProductCreate,
    ProductPriceCreate,
    ProductPriceResponse,
    ProductResponse,
    ProductUpdate,
)


class ProductService:
    def __init__(self, db: AsyncSession) -> None:
        self.repo = ProductRepository(db)
        self.price_repo = ProductPriceRepository(db)

    async def list_products(self, merchant_id: str) -> list[ProductResponse]:
        products = await self.repo.list(merchant_id)
        return [ProductResponse.model_validate(p) for p in products]

    async def get_product(self, product_id: uuid.UUID, merchant_id: str) -> ProductResponse:
        product = await self._get_owned_or_404(product_id, merchant_id)
        return ProductResponse.model_validate(product)

    async def create_product(
        self, merchant_id: str, data: ProductCreate
    ) -> ProductResponse:
        product = await self.repo.create(
            merchant_id=merchant_id,
            name=data.name,
            description=data.description,
            base_amount=data.base_amount,
            base_currency=data.base_currency,
            auto_pricing_enabled=data.auto_pricing_enabled,
        )
        return ProductResponse.model_validate(product)

    async def update_product(
        self, product_id: uuid.UUID, merchant_id: str, data: ProductUpdate
    ) -> ProductResponse:
        product = await self._get_owned_or_404(product_id, merchant_id)
        updates = data.model_dump(exclude_unset=True)
        updated = await self.repo.update(product, **updates)
        return ProductResponse.model_validate(updated)

    async def delete_product(self, product_id: uuid.UUID, merchant_id: str) -> None:
        product = await self._get_owned_or_404(product_id, merchant_id)
        await self.repo.delete(product)

    async def list_prices(
        self, product_id: uuid.UUID, merchant_id: str
    ) -> list[ProductPriceResponse]:
        await self._get_owned_or_404(product_id, merchant_id)
        prices = await self.price_repo.list_by_product(product_id)
        return [ProductPriceResponse.model_validate(p) for p in prices]

    async def create_price(
        self, product_id: uuid.UUID, merchant_id: str, data: ProductPriceCreate
    ) -> ProductPriceResponse:
        await self._get_owned_or_404(product_id, merchant_id)
        price = await self.price_repo.create(
            product_id=product_id,
            asset=data.asset,
            chain=data.chain,
            amount=data.amount,
        )
        return ProductPriceResponse.model_validate(price)

    async def _get_owned_or_404(
        self, product_id: uuid.UUID, merchant_id: str
    ) -> Product:
        """Return product if it exists and belongs to merchant, else raise 404."""
        product = await self.repo.get(product_id)
        if product is None or product.merchant_id != merchant_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found",
            )
        return product


def get_product_service(db: AsyncSession = Depends(get_db)) -> ProductService:
    """FastAPI dependency that returns a ProductService instance."""
    return ProductService(db)
