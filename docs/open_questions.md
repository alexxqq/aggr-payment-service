# Open Questions

## OQ-001: PaymentIntent amount type
**Question:** Should `amount` be stored as `Numeric(36,18)` (token precision) or as a separate integer in base units?
**Assumption:** Using `Numeric(36,18)` for human-readable amounts. Will revisit when Blockchain Core integration is defined.

## OQ-002: Merchant ID format
**Question:** Is `merchant_id` a Firebase UID (string) or an internal UUID?
**Assumption:** Treating it as a string (`varchar(128)`) to be compatible with both. User Service is source of truth.

## OQ-003: User Service internal endpoint spec
**Status: RESOLVED (2026-04-14)**
Primary endpoint: `GET /internal/merchant/{merchant_id}/capabilities`
Returns: `{merchant_id, status, is_active, allowed_chains, allowed_assets, default_chain}`
Full config: `GET /internal/merchant/{merchant_id}/config`
Legacy compat: `GET /internal/merchants/{merchant_id}` (plural, kept for backward compat)

## OQ-004: Authentication on Payment Service endpoints
**Question:** How are merchant-facing endpoints authenticated? Firebase token via API Gateway? Or direct Firebase verification?
**Assumption:** For MVP, authentication is handled by API Gateway. Payment Service trusts `X-Merchant-ID` header passed by gateway. Not implementing Firebase verification here.

## OQ-005: AnalyticsSnapshot computation
**Question:** What process creates AnalyticsSnapshot rows?
**Assumption:** Background job (cron/worker) outside MVP scope. Table and model exist, API read endpoint to be added later.
