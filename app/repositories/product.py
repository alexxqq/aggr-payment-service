"""Repositories for Product and ProductPrice."""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_price import ProductPrice


class ProductRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list(self, merchant_id: str) -> list[Product]:
        result = await self.db.execute(
            select(Product)
            .where(Product.merchant_id == merchant_id)
            .order_by(Product.created_at.desc())
        )
        return list(result.scalars().all())

    async def get(self, product_id: uuid.UUID) -> Product | None:
        result = await self.db.execute(
            select(Product).where(Product.id == product_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        merchant_id: str,
        name: str,
        description: str | None,
        base_amount: Decimal | None = None,
        base_currency: str | None = None,
        auto_pricing_enabled: bool | None = None,
    ) -> Product:
        product = Product(
            merchant_id=merchant_id,
            name=name,
            description=description,
            base_amount=base_amount,
            base_currency=base_currency,
            auto_pricing_enabled=auto_pricing_enabled,
        )
        self.db.add(product)
        await self.db.flush()
        await self.db.refresh(product)
        return product

    async def update(self, product: Product, **kwargs: object) -> Product:
        for key, value in kwargs.items():
            if value is not None:
                setattr(product, key, value)
        await self.db.flush()
        await self.db.refresh(product)
        return product

    async def delete(self, product: Product) -> None:
        await self.db.delete(product)
        await self.db.flush()


class ProductPriceRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_by_product(self, product_id: uuid.UUID) -> list[ProductPrice]:
        result = await self.db.execute(
            select(ProductPrice)
            .where(ProductPrice.product_id == product_id)
            .order_by(ProductPrice.created_at.desc())
        )
        return list(result.scalars().all())

    async def get(self, price_id: uuid.UUID) -> ProductPrice | None:
        result = await self.db.execute(
            select(ProductPrice).where(ProductPrice.id == price_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        product_id: uuid.UUID,
        asset: str,
        chain: str,
        amount: str,
    ) -> ProductPrice:
        from decimal import Decimal
        price = ProductPrice(
            product_id=product_id,
            asset=asset,
            chain=chain,
            amount=Decimal(str(amount)),
        )
        self.db.add(price)
        await self.db.flush()
        await self.db.refresh(price)
        return price
