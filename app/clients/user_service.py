"""Internal HTTP client for User Service.

Communicates via X-Internal-Secret header.
User Service is the source of truth for merchant identity, capabilities,
allowed chains/assets, payout wallets, and webhook configuration.
"""

from dataclasses import dataclass

import httpx

from app.core.config import get_settings


@dataclass
class MerchantCapabilities:
    """Parsed response from GET /internal/merchant/{id}/capabilities."""

    merchant_id: str
    is_active: bool
    allowed_chains: list[str]
    allowed_assets: list[str]
    default_chain: str | None


class UserServiceClient:
    """Thin HTTP client for calling User Service internal endpoints."""

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.user_service_url
        self._secret = settings.internal_api_secret

    def _headers(self) -> dict[str, str]:
        return {"X-Internal-Secret": self._secret}

    async def get_merchant_capabilities(
        self, merchant_id: str
    ) -> MerchantCapabilities:
        """Fetch merchant capabilities from User Service.

        Returns parsed MerchantCapabilities.

        Raises:
            httpx.HTTPStatusError: on 4xx/5xx response from User Service.
                response.status_code == 404 means merchant not found.
            httpx.ConnectError: when User Service is unreachable.
            httpx.TimeoutException: when the request times out.
        """
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{self._base_url}/internal/merchant/{merchant_id}/capabilities",
                headers=self._headers(),
            )
            response.raise_for_status()
            data = response.json()
            return MerchantCapabilities(
                merchant_id=str(data["merchant_id"]),
                is_active=data["is_active"],
                allowed_chains=data["allowed_chains"],
                allowed_assets=data["allowed_assets"],
                default_chain=data.get("default_chain"),
            )

    async def get_merchant(self, merchant_id: str) -> dict:
        """Fetch full merchant config from User Service.

        Returns raw dict including status, wallets, webhook_url, webhook_enabled,
        webhook_secret (for HMAC signing), and limits.
        Raises httpx.HTTPStatusError on non-2xx responses.
        """
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{self._base_url}/internal/merchant/{merchant_id}/config",
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()

    async def is_merchant_active(self, merchant_id: str) -> bool:
        """Return True if the merchant exists and is active."""
        caps = await self.get_merchant_capabilities(merchant_id)
        return caps.is_active

    async def get_allowed_chains(self, merchant_id: str) -> list[str]:
        """Return list of chain identifiers allowed for this merchant."""
        caps = await self.get_merchant_capabilities(merchant_id)
        return caps.allowed_chains

    async def get_allowed_assets(self, merchant_id: str) -> list[str]:
        """Return list of asset symbols allowed for this merchant."""
        caps = await self.get_merchant_capabilities(merchant_id)
        return caps.allowed_assets

    async def get_payout_wallet(self, merchant_id: str, chain: str) -> str | None:
        """Return default payout wallet address for the given merchant and chain.

        Fetches full config and finds the default wallet for the requested chain.
        Returns None if no matching wallet exists.
        """
        config = await self.get_merchant(merchant_id)
        for wallet in config.get("wallets", []):
            if wallet.get("chain") == chain and wallet.get("is_default"):
                return wallet.get("address")
        return None


def get_user_service_client() -> UserServiceClient:
    """FastAPI dependency that returns a UserServiceClient instance."""
    return UserServiceClient()
