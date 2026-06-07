# Payment Service Development Rules

## Project context

This repository contains only the Payment Service of the thesis system.

Payment Service is the merchant commerce layer.

The Payment Service owns:
- products
- product prices / plans
- paywalls
- invoices / payment intents
- payment statuses
- payment event history
- analytics summaries
- checkout-related metadata

The Payment Service uses User Service for:
- merchant status
- merchant capabilities
- allowed chains
- allowed assets
- payout wallets
- webhook configuration

The Payment Service must NOT:
- execute blockchain transactions directly
- estimate gas via RPC directly
- store private keys
- own merchant identity/configuration as source of truth

## Architecture constraints

- Use FastAPI
- Use PostgreSQL
- Use SQLAlchemy + Alembic
- Keep clear separation between API, service, repository, and client layers
- Use an internal client for User Service communication
- Preserve strict domain boundaries
- Prefer small, testable changes

## External dependencies

User Service is treated as an upstream internal dependency.
For MVP, service-to-service calls may use:
- X-Internal-Secret
- internal HTTP requests

Do not reimplement User Service logic locally.
Do not duplicate merchant configuration as source of truth.

## Required domain objects

Implement and maintain support for:
- Product
- ProductPrice
- Paywall
- Invoice or PaymentIntent
- PaymentEvent
- AnalyticsSnapshot

## Expected responsibilities

This service should provide:
- product CRUD
- product price CRUD
- paywall CRUD
- payment intent / invoice creation
- payment status tracking
- payment event history
- basic merchant-facing analytics summaries
- webhook orchestration hooks or skeleton
- preparation of execution requests for Blockchain Core integration

## Workflow rules

For every task:
1. Read spec/service_scope.md and spec/acceptance_checklist.md
2. Inspect existing code before changing anything
3. Write a short implementation plan to docs/plan.md
4. Reuse existing code where possible
5. Implement the smallest correct change
6. Add or update tests
7. Run formatting, linting, and tests
8. Update docs/test_report.md
9. Update spec/acceptance_checklist.md

## Integration rules

Before creating or confirming a payment-related entity:
- verify merchant status/capabilities through User Service when relevant
- do not assume every merchant is active
- do not assume every chain or asset is allowed

## Safety rules

- Do not rewrite the whole service unless absolutely necessary
- Do not mix blockchain execution logic into this service
- Do not add wallet private key handling
- Do not invent unrelated architecture layers
- If something is ambiguous, record it in docs/open_questions.md and continue with the safest MVP assumption

## Definition of done

A task is done only if:
- code is implemented
- migrations are created if schema changed
- tests pass
- service starts in docker-compose
- docs are updated
- acceptance checklist is updated