"""Repository for CheckoutSession."""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.checkout_session import CheckoutSession


class CheckoutSessionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, session_id: uuid.UUID) -> CheckoutSession | None:
        result = await self.db.execute(
            select(CheckoutSession).where(CheckoutSession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def list_by_merchant(self, merchant_id: str) -> list[CheckoutSession]:
        result = await self.db.execute(
            select(CheckoutSession)
            .where(CheckoutSession.merchant_id == merchant_id)
            .order_by(CheckoutSession.created_at.desc())
        )
        return list(result.scalars().all())

    async def create(
        self,
        merchant_id: str,
        amount: Decimal,
        currency: str,
        success_redirect_url: str | None = None,
        cancel_redirect_url: str | None = None,
        asset: str | None = None,
        chain: str | None = None,
        metadata_json: str | None = None,
        expires_in_minutes: int = 60,
    ) -> CheckoutSession:
        expires_at = datetime.now(datetime.now().astimezone().tzinfo) + timedelta(
            minutes=expires_in_minutes
        )
        session = CheckoutSession(
            merchant_id=merchant_id,
            amount=amount,
            currency=currency,
            success_redirect_url=success_redirect_url,
            cancel_redirect_url=cancel_redirect_url,
            asset=asset,
            chain=chain,
            metadata_json=metadata_json,
            expires_at=expires_at,
        )
        self.db.add(session)
        await self.db.flush()
        return session

    async def mark_used(
        self, session_id: uuid.UUID, payment_intent_id: uuid.UUID
    ) -> None:
        session = await self.get(session_id)
        if session:
            session.used_by_payment_intent_id = payment_intent_id
            await self.db.flush()
