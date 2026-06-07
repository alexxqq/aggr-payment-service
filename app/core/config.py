"""Environment-based configuration."""

from decimal import Decimal
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    host: str = "0.0.0.0"
    port: int = 8001

    database_url: str = (
        "postgresql+asyncpg://payment:password@localhost:5434/payment_service_db"
    )

    internal_api_secret: str = "your-internal-service-secret-change-in-production"

    # User Service
    user_service_url: str = "http://localhost:8002"

    # Blockchain Core
    blockchain_core_url: str = "http://localhost:8003"

    # Aggregator hot wallets — funds from customers land here first.
    # Merchants withdraw from our balance to their own wallets later.
    # Override per chain via env: AGGREGATOR_WALLET_ETHEREUM, etc.
    aggregator_wallet_ethereum: str = ""
    aggregator_wallet_bsc: str = ""
    aggregator_wallet_tron: str = ""
    aggregator_wallet_arbitrum: str = ""
    aggregator_wallet_polygon: str = ""

    def get_aggregator_wallet(self, chain: str) -> str | None:
        """Return aggregator hot wallet address for the given chain, or None if not configured."""
        mapping = {
            "ethereum": self.aggregator_wallet_ethereum,
            "bsc": self.aggregator_wallet_bsc,
            "tron": self.aggregator_wallet_tron,
            "arbitrum": self.aggregator_wallet_arbitrum,
            "polygon": self.aggregator_wallet_polygon,
        }
        addr = mapping.get(chain.lower(), "")
        return addr or None

    # ── Price Oracle (CoinGecko) ────────────────────────────────────────────────
    coingecko_api_key: str = ""
    coingecko_cache_ttl_seconds: int = 60  # Cache prices for 60 seconds

    # Safety defaults ONLY used if PriceOracle API is completely down for extended period
    # These should be updated monthly to stay close to reality
    price_fallback_eth_usd: str = "1560"  # Current ETH price (update monthly!)
    price_fallback_pol_usd: str = "0.54"  # Current POL price (update monthly!)
    price_fallback_usdc_usd: str = "1.00"
    price_fallback_usdt_usd: str = "1.00"

    def get_quote_rate(self, base_currency: str, asset: str) -> Decimal | None:
        """Return units-of-asset per 1 unit-of-base-currency, or None if rate not configured.

        Args:
            base_currency: fiat currency (e.g. "USD")
            asset: crypto asset (e.g. "ETH", "USDC", "MATIC")

        Returns:
            Decimal with the exchange rate, or None if unknown.
        """
        if base_currency.upper() != "USD":
            return None
        key = f"quote_rate_usd_{asset.lower()}"
        raw = getattr(self, key, None)
        if raw is None:
            return None
        try:
            return Decimal(raw)
        except Exception:
            return None


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()
