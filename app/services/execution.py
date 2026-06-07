"""Execution request builder for Blockchain Core integration."""

import logging

from app.core.config import Settings, get_settings
from app.models.payment_intent import PaymentIntent
from app.schemas.execution import ExecutionRequestPayload

logger = logging.getLogger(__name__)


class ExecutionRequestBuilder:
    """Builds ExecutionRequestPayload from a PaymentIntent.

    recipient_address = aggregator's own hot wallet for the chain.
    We receive customer payments into our wallets; the merchant receives
    a payout (withdrawal) from us separately.

    Falls back to the address already stored on the intent (set at creation
    time for checkout-originated intents).
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings  # None = resolve fresh on each build() call

    async def build(self, intent: PaymentIntent) -> ExecutionRequestPayload:
        # Resolve settings fresh each call so .env changes take effect without restart.
        settings = self._settings or get_settings()
        # Prefer the address already stored on the intent (set at checkout time).
        # Fall back to aggregator wallet config for manually-created intents.
        recipient_address = (
            intent.recipient_address
            or settings.get_aggregator_wallet(intent.chain)
        )
        if not recipient_address:
            logger.warning(
                "No aggregator wallet configured for chain '%s' — "
                "set AGGREGATOR_WALLET_%s in Payment Service .env",
                intent.chain,
                intent.chain.upper(),
            )
        return ExecutionRequestPayload(
            payment_intent_id=intent.id,
            merchant_id=intent.merchant_id,
            chain=intent.chain,
            asset=intent.asset,
            amount=str(intent.amount),
            payer_address=intent.payer_address,
            recipient_address=recipient_address,
            metadata=None,
            intent_created_at=intent.created_at,
        )
