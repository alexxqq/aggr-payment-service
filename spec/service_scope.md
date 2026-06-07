# Payment Service Scope

## Purpose

Payment Service is the merchant commerce layer.

## Owns
- products
- product prices / plans
- paywalls
- invoices / payment intents
- payment statuses
- payment event history
- analytics summaries
- checkout metadata

## Uses User Service for
- merchant config
- merchant status
- merchant capabilities
- allowed chains/assets
- payout wallets
- webhook config

## Must not own
- merchant identity as source of truth
- blockchain execution
- gas estimation via RPC
- private keys

## MVP entities
- Product
- ProductPrice
- Paywall
- Invoice or PaymentIntent
- PaymentEvent
- AnalyticsSnapshot

## MVP endpoints
- GET /health

- GET /v1/products
- POST /v1/products
- GET /v1/products/{product_id}
- PATCH /v1/products/{product_id}
- DELETE /v1/products/{product_id}

- GET /v1/products/{product_id}/prices
- POST /v1/products/{product_id}/prices
- PATCH /v1/prices/{price_id}
- DELETE /v1/prices/{price_id}

- GET /v1/paywalls
- POST /v1/paywalls
- GET /v1/paywalls/{paywall_id}
- PATCH /v1/paywalls/{paywall_id}
- DELETE /v1/paywalls/{paywall_id}

- POST /v1/payment-intents
- GET /v1/payment-intents/{payment_intent_id}
- GET /v1/payment-intents

- GET /v1/payment-intents/{payment_intent_id}/events

## Internal behavior
- validates merchant status/capabilities using User Service
- stores payment lifecycle from business perspective
- prepares execution request payload for future Blockchain Core integration

## Done criteria
- service runs in docker
- database migrations exist
- core endpoints work
- tests cover main flows
- User Service client works for key validations
