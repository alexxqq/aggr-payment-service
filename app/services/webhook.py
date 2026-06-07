"""Webhook dispatch service.

Fetches merchant webhook config from User Service, builds the
payment_intent.status_changed payload, signs it with HMAC-SHA256,
and dispatches an HTTP POST to the merchant's configured URL.

Status transitions remain resilient: dispatch errors are logged but
never propagated — a webhook failure must not roll back the transition.
"""

import hashlib
import hmac
import json
import logging

import httpx

from app.clients.user_service import UserServiceClient
from app.models.payment_intent import PaymentIntent

logger = logging.getLogger(__name__)

_WEBHOOK_TIMEOUT = 10.0
_WEBHOOK_RETRIES = 1


class WebhookPreparationService:
    """Builds, signs, and dispatches webhook payloads for payment_intent.status_changed.

    Responsibilities:
    - Fetch merchant webhook config from User Service.
    - If webhook is disabled or User Service is unavailable, skip silently.
    - Build the event payload.
    - Sign with HMAC-SHA256 if secret is available.
    - Dispatch HTTP POST to the merchant's webhook URL.
    - Log result; never propagate errors to callers.
    """

    def __init__(self, user_client: UserServiceClient) -> None:
        self._user_client = user_client

    async def prepare_and_log(
        self, intent: PaymentIntent, new_status: str
    ) -> dict | None:
        """Build webhook payload and dispatch HTTP POST.

        Returns the payload dict if dispatched, or None if skipped.
        Never raises — all errors are logged.
        """
        config = await self._fetch_merchant_config(intent.merchant_id)
        if config is None:
            return None

        webhook_cfg = config.get("webhook") or {}
        if not webhook_cfg.get("enabled"):
            logger.debug(
                "Webhook disabled for merchant=%s; skipping", intent.merchant_id
            )
            return None

        webhook_url = webhook_cfg.get("url")
        if not webhook_url:
            logger.debug(
                "Webhook URL missing for merchant=%s; skipping", intent.merchant_id
            )
            return None

        payload = {
            "event": "payment_intent.status_changed",
            "payment_intent_id": str(intent.id),
            "merchant_id": intent.merchant_id,
            "previous_status": intent.status,
            "new_status": new_status,
            "chain": intent.chain,
            "asset": intent.asset,
            "amount": str(intent.amount),
        }

        secret = webhook_cfg.get("secret")
        await self._dispatch(webhook_url, payload, secret)
        return payload

    async def _dispatch(
        self, url: str, payload: dict, secret: str | None
    ) -> None:
        """POST payload to webhook URL with optional HMAC-SHA256 signature.

        Retries once on connection/timeout errors. Logs all outcomes.
        Never raises.
        """
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        headers = {"Content-Type": "application/json"}

        if secret:
            sig = hmac.new(
                secret.encode(), body.encode(), hashlib.sha256
            ).hexdigest()
            headers["X-Webhook-Signature"] = f"sha256={sig}"

        attempts = _WEBHOOK_RETRIES + 1
        for attempt in range(1, attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=_WEBHOOK_TIMEOUT) as client:
                    response = await client.post(url, content=body, headers=headers)
                    response.raise_for_status()
                    logger.info(
                        "Webhook delivered: url=%s status=%d intent=%s",
                        url,
                        response.status_code,
                        payload.get("payment_intent_id"),
                    )
                    return
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "Webhook HTTP error (attempt %d/%d): url=%s status=%d intent=%s",
                    attempt,
                    attempts,
                    url,
                    exc.response.status_code,
                    payload.get("payment_intent_id"),
                )
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                logger.warning(
                    "Webhook connection error (attempt %d/%d): url=%s error=%s intent=%s",
                    attempt,
                    attempts,
                    url,
                    exc,
                    payload.get("payment_intent_id"),
                )
        logger.error(
            "Webhook delivery failed after %d attempt(s): url=%s intent=%s",
            attempts,
            url,
            payload.get("payment_intent_id"),
        )

    async def _fetch_merchant_config(self, merchant_id: str) -> dict | None:
        try:
            raw = await self._user_client.get_merchant(merchant_id)
            # Normalise User Service config dict into the expected shape:
            # { "webhook": { "enabled": bool, "url": str | None, "secret": str | None } }
            webhook_url = raw.get("webhook_url")
            webhook_enabled = raw.get("webhook_enabled", False)
            webhook_secret = raw.get("webhook_secret")
            return {
                "webhook": {
                    "enabled": webhook_enabled,
                    "url": webhook_url,
                    "secret": webhook_secret,
                }
            }
        except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as exc:
            logger.warning(
                "Could not fetch merchant config for webhook, merchant=%s: %s",
                merchant_id,
                exc,
            )
            return None
