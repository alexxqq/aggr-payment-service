# Payment Service — API Contract

Base URL: `/v1`

All merchant-facing endpoints require `X-Merchant-ID` header (injected by API Gateway).

## Health

| Method | Path      | Status      | Notes                     |
|--------|-----------|-------------|---------------------------|
| GET    | /health   | implemented | Returns {"status": "ok"}  |

## Products

Auth: `X-Merchant-ID` header required on all product endpoints.

| Method | Path                              | Status      | Notes                                      |
|--------|-----------------------------------|-------------|--------------------------------------------|
| GET    | /v1/products                      | implemented | Returns list for merchant                  |
| POST   | /v1/products                      | implemented | Body: {name, description?}; returns 201    |
| GET    | /v1/products/{product_id}         | implemented | 404 if not found or wrong merchant         |
| PATCH  | /v1/products/{product_id}         | implemented | Partial update; 404 if not found           |
| DELETE | /v1/products/{product_id}         | implemented | Returns 204; 404 if not found              |
| GET    | /v1/products/{product_id}/prices  | implemented | Returns price list for product             |
| POST   | /v1/products/{product_id}/prices  | implemented | Body: {asset, chain, amount}; returns 201  |

### ProductCreate body
```json
{"name": "string", "description": "string|null"}
```

### ProductUpdate body (all fields optional)
```json
{"name": "string", "description": "string", "is_active": true}
```

### ProductPriceCreate body
```json
{"asset": "USDC", "chain": "ethereum", "amount": "10.50"}
```
`amount` must be a valid decimal string greater than 0.

## Prices

| Method | Path                  | Status | Notes |
|--------|-----------------------|--------|-------|
| PATCH  | /v1/prices/{price_id} | stub   |       |
| DELETE | /v1/prices/{price_id} | stub   |       |

## Paywalls

Auth: `X-Merchant-ID` header required on all paywall endpoints.

| Method | Path                           | Status      | Notes                                         |
|--------|-------------------------------|-------------|-----------------------------------------------|
| GET    | /v1/paywalls                   | implemented | Returns list for merchant                     |
| POST   | /v1/paywalls                   | implemented | Body: {name, description?, product_ids?}; 201 |
| GET    | /v1/paywalls/{paywall_id}      | implemented | 404 if not found or wrong merchant            |
| PATCH  | /v1/paywalls/{paywall_id}      | implemented | Partial update; product_ids replaces the list |
| DELETE | /v1/paywalls/{paywall_id}      | implemented | Returns 204                                   |

### PaywallCreate body
```json
{"name": "string", "description": "string|null", "product_ids": ["uuid", ...]}
```

### PaywallUpdate body (all fields optional)
```json
{"name": "string", "description": "string", "product_ids": ["uuid", ...], "is_active": true}
```

## Payment Intents

Auth: `X-Merchant-ID` header required on all payment-intent endpoints.

| Method | Path                                           | Status      | Notes                                              |
|--------|------------------------------------------------|-------------|-----------------------------------------------------|
| POST   | /v1/payment-intents                            | implemented | Creates intent + initial "created" event; 201       |
| GET    | /v1/payment-intents                            | implemented | List for merchant; optional ?status= filter         |
| GET    | /v1/payment-intents/{id}                       | implemented | 404 if not found or wrong merchant                  |
| GET    | /v1/payment-intents/{id}/events                | implemented | Ordered by created_at asc; 404 if intent not owned  |

### PaymentIntentCreate body
```json
{
  "asset": "USDC",
  "chain": "ethereum",
  "amount": "10.50",
  "product_price_id": "uuid|null",
  "payer_address": "0x...|null",
  "metadata": {}
}
```
`amount` must be a positive decimal string.
`metadata` is stored as JSON and returned decoded.

### PaymentIntent creation validation (via User Service)
Before creating a PaymentIntent, the service validates:
1. Merchant exists in User Service → 422 "Merchant not found" if not
2. Merchant `is_active == true` → 422 "Merchant is not active" if not
3. Requested `chain` in merchant's `allowed_chains` → 422 "Chain '...' is not allowed"
4. Requested `asset` in merchant's `allowed_assets` → 422 "Asset '...' is not allowed"
5. User Service unreachable → 503 "User Service unavailable"

### PaymentIntent status lifecycle
`pending` → `confirmed` → `completed | failed | expired`

Valid transitions:
- `pending` → `confirmed`, `failed`, `expired`
- `confirmed` → `completed`, `failed`, `expired`
- Terminal states (`completed`, `failed`, `expired`) reject any transition.

### GET /v1/payment-intents/{id}/execution-request

Returns the execution payload that Blockchain Core needs to execute this payment.

Auth: `X-Merchant-ID` header (merchant must own the intent).

```json
{
  "payment_intent_id": "uuid",
  "merchant_id": "string",
  "chain": "ethereum",
  "asset": "USDC",
  "amount": "10.50",
  "payer_address": "0x...|null",
  "recipient_address": "0x...|null",
  "metadata": {}|null,
  "intent_created_at": "datetime"
}
```
`recipient_address` is the merchant's payout wallet (fetched from User Service);
`null` if User Service is unavailable (graceful degradation).

## Internal Endpoints

Auth: `X-Internal-Secret` header required. Not accessible from public API.

| Method | Path                                                | Status      | Notes                                         |
|--------|-----------------------------------------------------|-------------|-----------------------------------------------|
| POST   | /internal/payment-intents/{id}/transition           | implemented | Transitions status; appends PaymentEvent; 403 if secret invalid |

### StatusTransitionRequest body
```json
{"new_status": "confirmed", "data": {"tx_hash": "0x..."}|null}
```
`new_status` must be one of: `pending`, `confirmed`, `completed`, `failed`, `expired`.
Returns 422 if the transition is not allowed from the current status.

### PaymentEvent fields
`event_type`: created | status_changed | tx_submitted | tx_confirmed | expired | failed
`data_json`: raw JSON string (internal data, e.g. tx hash)
