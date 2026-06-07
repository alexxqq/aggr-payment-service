# Payment Service — Architecture

## Layers

```
app/
├── api/v1/          # FastAPI routers — request/response only
├── services/        # Business logic — orchestrates repos and clients
├── repositories/    # DB access — SQLAlchemy queries only
├── models/          # SQLAlchemy ORM models
├── schemas/         # Pydantic request/response schemas
├── clients/         # Internal HTTP clients (User Service)
└── core/            # Config, DB engine, shared deps
```

## Layer rules

- Routers call services (or return directly for simple cases)
- Services call repositories and clients
- Repositories receive an `AsyncSession` from `get_db` dependency
- Clients are injected via FastAPI dependency (`get_user_service_client`)
- Models are never exposed directly to routers — always go through schemas

## External dependencies

| Dependency   | Transport  | Auth             | Direction      |
|--------------|-----------|------------------|----------------|
| User Service | HTTP REST  | X-Internal-Secret| Payment → User |
| PostgreSQL   | asyncpg   | password         | internal only  |

## Key domain objects

| Entity             | Table                | Purpose                                 |
|--------------------|---------------------|-----------------------------------------|
| Product            | products            | Merchant's sellable item                |
| ProductPrice       | product_prices      | Price point per asset+chain             |
| Paywall            | paywalls            | Grouped product checkout page           |
| PaymentIntent      | payment_intents     | Payment request lifecycle               |
| PaymentEvent       | payment_events      | Immutable audit log per intent          |
| AnalyticsSnapshot  | analytics_snapshots | Daily pre-computed merchant summary     |

## Status: bootstrap (2026-04-14)

All layers scaffolded. Only /health is implemented. Business logic TBD.
