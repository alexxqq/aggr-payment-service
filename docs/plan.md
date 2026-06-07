# Payment Service — Implementation Plan

## Bootstrap task (2026-04-14)

### Goal
Create a runnable project foundation. No business logic yet. Health endpoint works. All future domain entities have model stubs and router stubs.

### What is being created

**Project config**
- `pyproject.toml` — uv-based project, same stack as user-service
- `requirements.txt` — locked flat list for Docker
- `.env.example` — all required env vars documented

**App skeleton**
- `app/main.py` — FastAPI app factory, lifespan, /health
- `app/core/config.py` — pydantic-settings, reads from env
- `app/core/db.py` — async SQLAlchemy engine, session dependency, Base

**Models (stubs — tables exist, columns minimal for now)**
- `app/models/product.py` — Product
- `app/models/product_price.py` — ProductPrice
- `app/models/paywall.py` — Paywall
- `app/models/payment_intent.py` — PaymentIntent
- `app/models/payment_event.py` — PaymentEvent
- `app/models/analytics_snapshot.py` — AnalyticsSnapshot
- `app/models/__init__.py` — exports all models for Alembic

**API stubs**
- `app/api/v1/router.py` — combines all sub-routers
- `app/api/v1/products.py` — stub (501)
- `app/api/v1/prices.py` — stub (501)
- `app/api/v1/paywalls.py` — stub (501)
- `app/api/v1/payment_intents.py` — stub (501)

**User Service client skeleton**
- `app/clients/__init__.py`
- `app/clients/user_service.py` — stub class with placeholder methods

**Alembic**
- `alembic.ini`
- `alembic/env.py` — imports all models, uses sync psycopg2
- `alembic/versions/0001_initial_schema.py` — creates all 6 tables

**Docker**
- `Dockerfile` — uv-based, non-root user
- `docker-compose.yml` — payment-service + postgres on port 5434
- `.dockerignore`

**Tests**
- `tests/conftest.py` — shared fixtures (app, client, mock db)
- `tests/unit/__init__.py`
- `tests/unit/test_health.py` — GET /health → 200

**Docs**
- `docs/architecture.md` — service layers described
- `docs/api_contract.md` — endpoint list (status: stub)
- `docs/test_report.md` — updated after bootstrap
- `docs/open_questions.md` — known open questions

### What comes next (not in this task)

1. ~~Implement Product CRUD~~ → done in task 2
2. ~~Implement ProductPrice CRUD~~ → done in task 2
3. ~~Implement Paywall CRUD~~ → done in task 3
4. ~~Implement PaymentIntent creation + retrieval~~ → done in task 3
5. ~~Implement PaymentEvent history~~ → done in task 3
6. Implement User Service client (merchant status check)
7. Wire User Service check into PaymentIntent creation
8. AnalyticsSnapshot (read-only summary)
9. Integration tests

---

## Task 3 — Paywall CRUD + PaymentIntent flow (2026-04-14)

### Goal
Implement Paywall CRUD and basic PaymentIntent create/retrieve flow with initial event recording.

### Key design decisions

**Paywall.product_ids**
- Stored as `ARRAY(UUID(as_uuid=False))` → Python `list[str]` from ORM
- Schema uses `list[UUID]`; Pydantic coerces str→UUID on read, UUID→str in repo on write
- Replace semantics on update (not append)

**PaymentIntent.amount**
- DB column is NUMERIC, ORM returns Decimal; response schema converts with `str()`
- Input validated as positive decimal string

**PaymentIntent.metadata_json**
- Stored as TEXT; service layer JSON-encodes on create, decodes on read
- Response schema has `metadata: dict | None` (not the raw string field)

**PaymentEvent creation**
- `event_type="created"`, `to_status="pending"` appended in same DB flush as intent
- Events are immutable append-only records

**Merchant identity**
- All endpoints use `X-Merchant-ID` header
- List/get/events all scope to merchant; cross-merchant access returns 404

**PaymentIntent listing**
- Optional `status` query param filter

### Files being created/updated

- `app/schemas/paywall.py` — PaywallCreate, PaywallUpdate, PaywallResponse
- `app/schemas/payment_intent.py` — PaymentIntentCreate, PaymentIntentResponse, PaymentEventResponse
- `app/repositories/paywall.py` — PaywallRepository
- `app/repositories/payment_intent.py` — PaymentIntentRepository, PaymentEventRepository
- `app/services/paywall.py` — PaywallService + get_paywall_service
- `app/services/payment_intent.py` — PaymentIntentService + get_payment_intent_service
- `app/api/v1/paywalls.py` — replace stubs
- `app/api/v1/payment_intents.py` — replace stubs
- `tests/unit/test_paywalls.py`
- `tests/unit/test_payment_intents.py`

---

## Task 4 — User Service integration for PaymentIntent (2026-04-14)

### Goal
Wire real merchant validation into `PaymentIntentService.create`. No other endpoints change.

### Endpoint used from User Service
`GET /internal/merchant/{merchant_id}/capabilities`
Returns: `{merchant_id, status, is_active, allowed_chains, allowed_assets, default_chain}`

### Validation steps added to PaymentIntentService.create
1. Call `UserServiceClient.get_merchant_capabilities(merchant_id)`
2. If User Service returns 404 → 422 "Merchant not found"
3. If User Service unreachable/timeout → 503 "User Service unavailable"
4. If `is_active == False` → 422 "Merchant is not active"
5. If `chain not in allowed_chains` → 422 "Chain '{chain}' is not allowed for this merchant"
6. If `asset not in allowed_assets` → 422 "Asset '{asset}' is not allowed for this merchant"
7. If all checks pass → create intent + event as before

### Changes
- `app/clients/user_service.py` — implement `get_merchant_capabilities`, add `MerchantCapabilities` dataclass, keep helpers delegating to it
- `app/services/payment_intent.py` — accept `user_client` in `__init__`, add `_validate_merchant`, call it in `create`
- `app/api/v1/payment_intents.py` — `get_payment_intent_service` now also `Depends(get_user_service_client)`
- `tests/unit/test_payment_intent_validation.py` — service-level tests with mocked DB + mocked user client
- `docs/open_questions.md` — resolve OQ-003

---

## Task 5 — Execution request, status transitions, webhook preparation (2026-04-14)

### Goal
Prepare Payment Service for Blockchain Core integration without implementing actual execution.
Three concerns: (1) build execution payload, (2) transition status + append event, (3) prepare webhook payload.

### Execution request
- `ExecutionRequestPayload` — the data contract Blockchain Core needs
- `ExecutionRequestBuilder` service — combines intent data + payout wallet from User Service
- Payout wallet fetched from User Service on demand; graceful degradation if unavailable (null)
- New endpoint: `GET /v1/payment-intents/{id}/execution-request` (merchant-scoped)

### Status transitions
- Valid transitions: pending→{confirmed,failed,expired}, confirmed→{completed,failed,expired}
- Terminal states: completed, failed, expired — no further transitions
- Each transition appends a `status_changed` PaymentEvent (from_status, to_status, data_json)
- New internal endpoint: `POST /internal/payment-intents/{id}/transition` (X-Internal-Secret)
- Transition always succeeds even if webhook prep errors

### Webhook preparation
- `WebhookPreparationService` — fetches merchant webhook config from User Service
- Builds payload for `payment_intent.status_changed` event
- Logs prepared payload but does NOT dispatch HTTP request
- Returns None if webhook disabled or User Service unavailable

### New files
- `app/core/security.py` — verify_internal_secret dependency
- `app/schemas/execution.py` — ExecutionRequestPayload
- `app/services/execution.py` — ExecutionRequestBuilder
- `app/services/webhook.py` — WebhookPreparationService
- `app/api/internal.py` — POST /internal/payment-intents/{id}/transition
- `tests/unit/test_execution_request.py`
- `tests/unit/test_status_transition.py`
- `tests/unit/test_webhook_preparation.py`

### Modified files
- `app/schemas/payment_intent.py` — StatusTransitionRequest
- `app/repositories/payment_intent.py` — update_status method
- `app/services/payment_intent.py` — transition_status_internal, get_execution_request
- `app/api/v1/payment_intents.py` — GET /{id}/execution-request endpoint
- `app/main.py` — include internal router

---

## Task 2 — Product + ProductPrice CRUD (2026-04-14)

### Goal
Implement fully working Product and ProductPrice endpoints with tests.
Models already exist — only add schemas, repos, services, and fill in routers.

### Merchant identity
Merchant ID comes from `X-Merchant-ID` header (injected by API Gateway per OQ-004).
Not present in request body.

### What is being implemented

**Schemas** (`app/schemas/product.py`)
- `ProductCreate` — name, description
- `ProductUpdate` — name, description, is_active (all optional, PATCH semantics)
- `ProductResponse` — full product with id, merchant_id, timestamps
- `ProductPriceCreate` — asset, chain, amount (decimal string, validated > 0)
- `ProductPriceResponse` — full price with id, product_id, timestamps

**Repository** (`app/repositories/product.py`)
- `ProductRepository` — list(merchant_id), get(id), create, update, delete
- `ProductPriceRepository` — list_by_product(product_id), create

**Service** (`app/services/product.py`)
- `ProductService` — orchestrates repos, raises HTTP 404 for missing/wrong-merchant products
- `get_product_service` — FastAPI dependency

**Router** (`app/api/v1/products.py`)
- Replaces all stubs with real handlers
- Uses `X-Merchant-ID` header dependency for merchant identity

**Tests** (`tests/unit/test_products.py`)
- Router-level unit tests with service mocked via dependency override
- Covers 200/201/204/404/422 cases for all 7 endpoints
