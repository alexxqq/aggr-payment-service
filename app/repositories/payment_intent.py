"""Repositories for PaymentIntent and PaymentEvent."""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment_event import PaymentEvent
from app.models.payment_intent import PaymentIntent


class PaymentIntentRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_by_merchant(
        self, merchant_id: str, status: str | None = None
    ) -> list[PaymentIntent]:
        q = (
            select(PaymentIntent)
            .where(PaymentIntent.merchant_id == merchant_id)
            .order_by(PaymentIntent.created_at.desc())
        )
        if status is not None:
            q = q.where(PaymentIntent.status == status)
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def get(self, intent_id: uuid.UUID) -> PaymentIntent | None:
        result = await self.db.execute(
            select(PaymentIntent).where(PaymentIntent.id == intent_id)
        )
        return result.scalar_one_or_none()

    async def list_pending_by_chain(self, chain: str) -> list[PaymentIntent]:
        """Return all pending PaymentIntents for a given chain (used by monitor)."""
        result = await self.db.execute(
            select(PaymentIntent)
            .where(PaymentIntent.status == "pending")
            .where(PaymentIntent.chain == chain)
            .order_by(PaymentIntent.created_at.asc())
        )
        return list(result.scalars().all())

    async def update_status(
        self, intent: PaymentIntent, new_status: str
    ) -> PaymentIntent:
        intent.status = new_status
        await self.db.flush()
        await self.db.refresh(intent)
        return intent

    async def create(
        self,
        merchant_id: str,
        asset: str,
        chain: str,
        amount: str | Decimal,
        product_price_id: uuid.UUID | None = None,
        payer_address: str | None = None,
        recipient_address: str | None = None,
        metadata_json: str | None = None,
    ) -> PaymentIntent:
        intent = PaymentIntent(
            merchant_id=merchant_id,
            asset=asset,
            chain=chain,
            amount=Decimal(str(amount)),
            status="pending",
            product_price_id=product_price_id,
            payer_address=payer_address,
            recipient_address=recipient_address,
            metadata_json=metadata_json,
        )
        self.db.add(intent)
        await self.db.flush()
        await self.db.refresh(intent)
        return intent


class PaymentEventRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_by_intent(self, intent_id: uuid.UUID) -> list[PaymentEvent]:
        result = await self.db.execute(
            select(PaymentEvent)
            .where(PaymentEvent.payment_intent_id == intent_id)
            .order_by(PaymentEvent.created_at.asc())
        )
        return list(result.scalars().all())

    async def create(
        self,
        payment_intent_id: uuid.UUID,
        event_type: str,
        from_status: str | None = None,
        to_status: str | None = None,
        data_json: str | None = None,
    ) -> PaymentEvent:
        event = PaymentEvent(
            payment_intent_id=payment_intent_id,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            data_json=data_json,
        )
        self.db.add(event)
        await self.db.flush()
        await self.db.refresh(event)
        return event
