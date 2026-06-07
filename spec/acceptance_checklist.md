# Payment Service Acceptance Checklist

## Domain boundaries
- [x] Payment Service stores products, paywalls, invoices/payment intents, events, analytics
- [x] No merchant identity source-of-truth logic exists here
- [x] No blockchain transaction execution logic exists here
- [x] No private key storage exists here

## Data model
- [x] products table exists (model + migration)
- [x] product_prices table exists (model + migration)
- [x] paywalls table exists (model + migration)
- [x] payment_intents table exists (model + migration)
- [x] payment_events table exists (model + migration)
- [x] analytics_snapshots table exists (model + migration)

## API
- [x] GET /health returns 200
- [x] product CRUD works (GET list, POST, GET by id, PATCH, DELETE)
- [x] product price CRUD works (GET list by product, POST)
- [x] paywall CRUD works (GET list, POST, GET by id, PATCH, DELETE)
- [x] payment intent creation works (POST, validates merchant, creates initial event)
- [x] payment intent retrieval works (GET by id, GET list with optional status filter)
- [x] payment event history retrieval works (GET /events, scoped to merchant)

## Integration with User Service
- [x] User Service internal client exists (app/clients/user_service.py)
- [x] merchant status is checked before creating PaymentIntent (is_active)
- [x] allowed chains/assets are checked before creating PaymentIntent
- [x] internal auth is used consistently (X-Internal-Secret header)

## Quality
- [x] Alembic migrations exist (0001_initial_schema.py)
- [x] unit tests pass (97/97)
- [ ] integration tests pass
- [ ] docker startup works (blocked: docker group membership — environment issue)
- [x] execution request payload generation for Blockchain Core (GET /v1/payment-intents/{id}/execution-request)
- [x] status transitions implemented (POST /internal/payment-intents/{id}/transition)
- [x] webhook preparation skeleton (builds + logs payload; no HTTP dispatch)
- [x] internal endpoint protected by X-Internal-Secret
- [x] unit tests pass (97/97)
- [ ] integration tests pass
- [ ] docker startup works (blocked: docker group membership — environment issue)
- [x] docs are updated (architecture.md, api_contract.md, test_report.md, open_questions.md)
