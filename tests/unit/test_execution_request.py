"""Unit tests for ExecutionRequestBuilder."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.services.execution import ExecutionRequestBuilder


def _make_intent(
    merchant_id: str = "merchant-exec",
    chain: str = "ethereum",
    asset: str = "USDC",
    amount: str = "10.00",
    payer_address: str | None = "0xpayer",
    recipient_address: str | None = None,
) -> MagicMock:
    m = MagicMock()
    m.id = uuid4()
    m.merchant_id = merchant_id
    m.chain = chain
    m.asset = asset
    m.amount = amount
    m.payer_address = payer_address
    m.recipient_address = recipient_address
    m.created_at = datetime.now(timezone.utc)
    return m


def _make_builder(aggregator_wallet: str | None = "0xrecipient") -> ExecutionRequestBuilder:
    mock_settings = MagicMock()
    mock_settings.get_aggregator_wallet.return_value = aggregator_wallet
    return ExecutionRequestBuilder(settings=mock_settings)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_returns_correct_fields():
    intent = _make_intent()
    builder = _make_builder(aggregator_wallet="0xrecipient")
    payload = await builder.build(intent)
    assert payload.payment_intent_id == intent.id
    assert payload.merchant_id == intent.merchant_id
    assert payload.chain == intent.chain
    assert payload.asset == intent.asset
    assert payload.amount == str(intent.amount)
    assert payload.payer_address == intent.payer_address
    assert payload.recipient_address == "0xrecipient"
    assert payload.intent_created_at == intent.created_at


@pytest.mark.asyncio
async def test_build_uses_intent_recipient_when_set():
    """recipient_address stored on the intent takes priority over aggregator wallet."""
    intent = _make_intent(recipient_address="0xintent_wallet")
    builder = _make_builder(aggregator_wallet="0xaggregator")
    payload = await builder.build(intent)
    assert payload.recipient_address == "0xintent_wallet"


@pytest.mark.asyncio
async def test_build_falls_back_to_aggregator_wallet():
    intent = _make_intent(recipient_address=None)
    builder = _make_builder(aggregator_wallet="0xaggregator")
    payload = await builder.build(intent)
    assert payload.recipient_address == "0xaggregator"


# ---------------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_recipient_none_when_no_wallet():
    intent = _make_intent(recipient_address=None)
    builder = _make_builder(aggregator_wallet=None)
    payload = await builder.build(intent)
    assert payload.recipient_address is None
