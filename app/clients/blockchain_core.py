"""Internal HTTP client for Blockchain Core.

Creates execution requests and triggers stub execution.
Communicates via X-Internal-Secret header.
"""

from decimal import Decimal
from uuid import UUID

import httpx

from app.core.config import get_settings


class BlockchainCoreClient:
    """Thin HTTP client for calling Blockchain Core internal endpoints."""

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.blockchain_core_url.rstrip("/")
        self._secret = settings.internal_api_secret

    def _headers(self) -> dict[str, str]:
        return {
            "X-Internal-Secret": self._secret,
            "Content-Type": "application/json",
        }

    async def create_execution_request(
        self,
        invoice_id: UUID,
        merchant_id: UUID,
        chain: str,
        asset: str,
        amount: Decimal,
        recipient_address: str,
    ) -> dict:
        """
        POST /internal/execution-requests

        Creates an ExecutionRequest in Blockchain Core with status 'created'.
        Returns the created record as a dict.

        Raises:
            httpx.HTTPStatusError: on 4xx/5xx from Blockchain Core.
            httpx.ConnectError / httpx.TimeoutException: when unreachable.
        """
        body = {
            "invoice_id": str(invoice_id),
            "merchant_id": str(merchant_id),
            "chain": chain,
            "asset": asset,
            "amount": str(amount),
            "recipient_address": recipient_address,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self._base_url}/internal/execution-requests",
                json=body,
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()

    async def trigger_execution(self, execution_request_id: UUID) -> dict:
        """
        POST /internal/execution-requests/{id}/execute

        Triggers the stub execution lifecycle:
          created → processing → confirmed

        Blockchain Core will call back to Payment Service with the confirmed
        status before this call returns.

        Returns the updated ExecutionRequest record as a dict.

        Raises:
            httpx.HTTPStatusError: on 4xx/5xx (e.g. 409 already executed).
            httpx.ConnectError / httpx.TimeoutException: when unreachable.
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._base_url}/internal/execution-requests/{execution_request_id}/execute",
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()


    async def estimate_gas(
        self,
        chain: str,
        asset: str = "ETH",
        transfer_type: str | None = None,
        to_address: str | None = None,
        amount_raw: int | None = None,
    ) -> dict | None:
        """POST /internal/gas/estimate — estimate gas for chain+asset.

        Returns response dict with gas_units, gas_price_wei, total_fee_wei, etc.
        Returns None if Blockchain Core is unavailable or estimation fails.
        """
        body: dict = {"chain": chain, "asset": asset}
        if transfer_type:
            body["transfer_type"] = transfer_type
        if to_address:
            body["to_address"] = to_address
        if amount_raw is not None:
            body["amount_raw"] = amount_raw
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self._base_url}/internal/gas/estimate",
                    json=body,
                    headers=self._headers(),
                )
                response.raise_for_status()
                return response.json()
        except Exception:
            return None

    async def get_deposit_address(self, intent_id: str) -> str | None:
        """POST /internal/deposit-address — returns a unique deposit address for an intent.

        Returns None if Blockchain Core is unavailable (caller falls back to shared wallet).
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{self._base_url}/internal/deposit-address",
                    json={"intent_id": intent_id},
                    headers=self._headers(),
                )
                response.raise_for_status()
                return response.json()["address"]
        except Exception:
            return None


def get_blockchain_core_client() -> BlockchainCoreClient:
    """FastAPI dependency that returns a BlockchainCoreClient instance."""
    return BlockchainCoreClient()
