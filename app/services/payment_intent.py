"""Service layer for PaymentIntent and PaymentEvent."""

import json
import logging
import uuid
from decimal import Decimal
from uuid import UUID

import httpx
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.blockchain_core import BlockchainCoreClient, get_blockchain_core_client
from app.clients.user_service import UserServiceClient, get_user_service_client
from app.core.db import get_db
from app.models.payment_intent import PaymentIntent
from app.repositories.payment_intent import PaymentEventRepository, PaymentIntentRepository
from app.schemas.execution import ExecutionRequestPayload
from app.schemas.payment_intent import (
    PaymentEventResponse,
    PaymentIntentCreate,
    PaymentIntentResponse,
)
from app.services.execution import ExecutionRequestBuilder
from app.services.webhook import WebhookPreparationService

logger = logging.getLogger(__name__)

# Valid status transitions; terminal states map to empty set.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"confirmed", "failed", "expired"},
    "confirmed": {"completed", "failed", "expired"},
    "completed": set(),
    "failed": set(),
    "expired": set(),
}


class PaymentIntentService:
    def __init__(
        self,
        db: AsyncSession,
        user_client: UserServiceClient,
        blockchain_client: BlockchainCoreClient | None = None,
    ) -> None:
        self.repo = PaymentIntentRepository(db)
        self.event_repo = PaymentEventRepository(db)
        self.user_client = user_client
        self._execution_builder = ExecutionRequestBuilder()
        self._webhook_prep = WebhookPreparationService(user_client)
        self._blockchain_client = blockchain_client or BlockchainCoreClient()

    async def create(
        self, merchant_id: str, data: PaymentIntentCreate
    ) -> PaymentIntentResponse:
        await self._validate_merchant(merchant_id, data.chain, data.asset)

        metadata_json = json.dumps(data.metadata) if data.metadata is not None else None
        intent = await self.repo.create(
            merchant_id=merchant_id,
            asset=data.asset,
            chain=data.chain,
            amount=data.amount,
            product_price_id=data.product_price_id,
            payer_address=data.payer_address,
            metadata_json=metadata_json,
        )
        await self.event_repo.create(
            payment_intent_id=intent.id,
            event_type="created",
            to_status="pending",
        )
        return self._to_response(intent)

    async def get(
        self, intent_id: uuid.UUID, merchant_id: str
    ) -> PaymentIntentResponse:
        intent = await self._get_owned_or_404(intent_id, merchant_id)
        return self._to_response(intent)

    async def list_intents(
        self, merchant_id: str, status: str | None = None
    ) -> list[PaymentIntentResponse]:
        intents = await self.repo.list_by_merchant(merchant_id, status)
        return [self._to_response(i) for i in intents]

    async def list_events(
        self, intent_id: uuid.UUID, merchant_id: str
    ) -> list[PaymentEventResponse]:
        await self._get_owned_or_404(intent_id, merchant_id)
        events = await self.event_repo.list_by_intent(intent_id)
        return [PaymentEventResponse.model_validate(e) for e in events]

    async def get_execution_request(
        self, intent_id: uuid.UUID, merchant_id: str
    ) -> ExecutionRequestPayload:
        """Build an execution request payload for Blockchain Core.

        Ownership-checked: returns 404 if intent not found or wrong merchant.
        """
        intent = await self._get_owned_or_404(intent_id, merchant_id)
        return await self._execution_builder.build(intent)

    async def execute(
        self, intent_id: uuid.UUID, merchant_id: str
    ) -> PaymentIntentResponse:
        """Trigger stub execution for a pending PaymentIntent via Blockchain Core.

        Flow:
          1. Fetch and ownership-check the intent.
          2. Verify status is 'pending' (only pending intents can be executed).
          3. Build execution payload (resolves payout wallet from User Service).
          4. Validate recipient_address is available.
          5. Create ExecutionRequest in Blockchain Core.
          6. Trigger stub execution (Blockchain Core will callback to update status).
          7. Re-fetch and return the updated intent.

        Raises HTTPException on ownership failure, wrong status, missing wallet,
        or downstream service errors.
        """
        intent = await self._get_owned_or_404(intent_id, merchant_id)

        if intent.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Cannot execute: intent is in status '{intent.status}', expected 'pending'",
            )

        # Build execution payload — recipient is the aggregator's hot wallet
        payload = await self._execution_builder.build(intent)

        if not payload.recipient_address:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"Aggregator wallet not configured for chain '{intent.chain}'. "
                    f"Set AGGREGATOR_WALLET_{intent.chain.upper()} in Payment Service .env"
                ),
            )

        # Convert merchant_id str → UUID (merchant IDs are UUIDs from User Service)
        try:
            merchant_uuid = UUID(intent.merchant_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Invalid merchant_id format — expected UUID",
            )

        # Create execution request in Blockchain Core
        try:
            exec_req = await self._blockchain_client.create_execution_request(
                invoice_id=intent.id,
                merchant_id=merchant_uuid,
                chain=intent.chain,
                asset=intent.asset,
                amount=Decimal(str(intent.amount)),
                recipient_address=payload.recipient_address,
            )
        except httpx.HTTPStatusError as exc:
            logger.error("Blockchain Core rejected execution request: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Blockchain Core error: {exc.response.text[:200]}",
            ) from exc
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            logger.error("Blockchain Core unreachable: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Blockchain Core is unreachable",
            ) from exc

        execution_request_id = UUID(exec_req["id"])

        # Trigger stub execution — Blockchain Core transitions the request and
        # calls back POST /internal/payment-intents/{id}/transition synchronously
        try:
            await self._blockchain_client.trigger_execution(execution_request_id)
        except httpx.HTTPStatusError as exc:
            logger.error("Blockchain Core execution trigger failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Execution failed: {exc.response.text[:200]}",
            ) from exc
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            logger.error("Blockchain Core unreachable during execute: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Blockchain Core is unreachable",
            ) from exc

        # Re-fetch to pick up any status change from the callback
        updated = await self.repo.get(intent_id)
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment intent not found after execution",
            )
        return self._to_response(updated)

    async def transition_status_internal(
        self,
        intent_id: uuid.UUID,
        new_status: str,
        data: dict | None = None,
    ) -> PaymentIntentResponse:
        """Transition a PaymentIntent status (internal call, no ownership check).

        Validates the transition against ALLOWED_TRANSITIONS.
        Appends a status_changed PaymentEvent.
        Calls webhook preparation (errors are logged, not raised).
        """
        intent = await self.repo.get(intent_id)
        if intent is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment intent not found",
            )

        allowed = ALLOWED_TRANSITIONS.get(intent.status, set())
        if new_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"Cannot transition from '{intent.status}' to '{new_status}'"
                ),
            )

        old_status = intent.status
        intent = await self.repo.update_status(intent, new_status)

        data_json = json.dumps(data) if data is not None else None
        await self.event_repo.create(
            payment_intent_id=intent.id,
            event_type="status_changed",
            from_status=old_status,
            to_status=new_status,
            data_json=data_json,
        )

        # Webhook preparation: errors must not fail the transition.
        try:
            await self._webhook_prep.prepare_and_log(intent, new_status)
        except Exception:
            pass

        return self._to_response(intent)

    async def _validate_merchant(
        self, merchant_id: str, chain: str, asset: str
    ) -> None:
        """Check merchant status and capabilities via User Service.

        Raises HTTPException on validation failure or User Service error.
        """
        try:
            caps = await self.user_client.get_merchant_capabilities(merchant_id)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Merchant not found",
                )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="User Service returned an error",
            )
        except (httpx.ConnectError, httpx.TimeoutException):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="User Service unavailable",
            )

        if not caps.is_active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Merchant is not active",
            )
        if chain not in caps.allowed_chains:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Chain '{chain}' is not allowed for this merchant",
            )
        if asset not in caps.allowed_assets:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Asset '{asset}' is not allowed for this merchant",
            )

    def _to_response(self, intent: PaymentIntent) -> PaymentIntentResponse:
        return PaymentIntentResponse(
            id=intent.id,
            merchant_id=intent.merchant_id,
            product_price_id=intent.product_price_id,
            asset=intent.asset,
            chain=intent.chain,
            amount=str(intent.amount),
            status=intent.status,
            payer_address=intent.payer_address,
            recipient_address=intent.recipient_address,
            metadata=json.loads(intent.metadata_json) if intent.metadata_json else None,
            expires_at=intent.expires_at,
            created_at=intent.created_at,
            updated_at=intent.updated_at,
        )

    async def _get_owned_or_404(
        self, intent_id: uuid.UUID, merchant_id: str
    ) -> PaymentIntent:
        intent = await self.repo.get(intent_id)
        if intent is None or intent.merchant_id != merchant_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment intent not found",
            )
        return intent


def get_payment_intent_service(
    db: AsyncSession = Depends(get_db),
    user_client: UserServiceClient = Depends(get_user_service_client),
    blockchain_client: BlockchainCoreClient = Depends(get_blockchain_core_client),
) -> PaymentIntentService:
    """FastAPI dependency that returns a PaymentIntentService instance."""
    return PaymentIntentService(db, user_client, blockchain_client)
