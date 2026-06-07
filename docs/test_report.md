# Payment Service — Test Report

## 2026-04-14 — Task 5: Execution request, status transitions, webhook prep

### Environment
- Python 3.10.12, pytest 9.0.3, pytest-asyncio 1.3.0
- httpx ASGI transport, unittest.mock

### Results

| Test file                                        | Tests | Passed | Failed | Notes                                                        |
|--------------------------------------------------|-------|--------|--------|--------------------------------------------------------------|
| tests/unit/test_health.py                        | 1     | 1      | 0      | GET /health → 200                                            |
| tests/unit/test_products.py                      | 22    | 22     | 0      | Product + ProductPrice endpoints                             |
| tests/unit/test_paywalls.py                      | 16    | 16     | 0      | Paywall CRUD endpoints                                       |
| tests/unit/test_payment_intents.py               | 19    | 19     | 0      | PaymentIntent router (service fully mocked)                  |
| tests/unit/test_payment_intent_validation.py     | 14    | 14     | 0      | Service-level validation via mocked UserService              |
| tests/unit/test_execution_request.py             | 8     | 8      | 0      | ExecutionRequestBuilder: happy path + graceful degradation   |
| tests/unit/test_status_transition.py             | 12    | 12     | 0      | transition_status_internal: valid/invalid/404/webhook-error  |
| tests/unit/test_webhook_preparation.py           | 8     | 8      | 0      | WebhookPreparationService: enabled/disabled/unavailable      |

**Total: 97 passed, 0 failed**

### Linting

| Tool | Result | Notes             |
|------|--------|-------------------|
| ruff | PASS   | All checks passed |

### Service startup

| Method        | Result  | Notes                                     |
|---------------|---------|-------------------------------------------|
| uvicorn local | OK      | App starts, no import errors              |
| docker compose| blocked | User not in docker group (env limitation) |

### New functionality tested

| Scenario                                             | Expected | Test |
|------------------------------------------------------|----------|------|
| ExecutionRequestPayload has correct fields           | —        | ✓    |
| Payout wallet fetched via User Service               | —        | ✓    |
| recipient_address=None when User Service unavailable | —        | ✓    |
| recipient_address=None on HTTP/connect/timeout error | —        | ✓    |
| pending→confirmed transition succeeds                | 200      | ✓    |
| status_changed event appended on transition          | —        | ✓    |
| data_json stored in transition event                 | —        | ✓    |
| Invalid transition (pending→completed) rejected      | 422      | ✓    |
| Terminal state rejects any further transition        | 422      | ✓    |
| Missing intent returns 404                           | 404      | ✓    |
| Webhook error does not fail transition               | —        | ✓    |
| Webhook payload built correctly when enabled         | —        | ✓    |
| Webhook returns None when disabled                   | —        | ✓    |
| Webhook returns None when User Service unavailable   | —        | ✓    |

### Known gaps

- No integration tests (require running Postgres + User Service)
- AnalyticsSnapshot endpoints not yet implemented
- Webhook HTTP dispatch not implemented (skeleton only)

### How to run

```bash
pip install fastapi uvicorn sqlalchemy asyncpg psycopg2-binary alembic \
            pydantic pydantic-settings httpx pytest pytest-asyncio ruff

pytest tests/unit -q     # unit tests only
pytest -q                # all tests
ruff check app tests     # lint
```

---

## 2026-04-14 — Task 4: User Service integration

### Environment
- Python 3.10.12, pytest 9.0.3, pytest-asyncio 1.3.0
- httpx ASGI transport, unittest.mock

### Results

| Test file                                      | Tests | Passed | Failed | Notes                                             |
|------------------------------------------------|-------|--------|--------|---------------------------------------------------|
| tests/unit/test_health.py                      | 1     | 1      | 0      | GET /health → 200                                 |
| tests/unit/test_products.py                    | 22    | 22     | 0      | Product + ProductPrice endpoints                  |
| tests/unit/test_paywalls.py                    | 16    | 16     | 0      | Paywall CRUD endpoints                            |
| tests/unit/test_payment_intents.py             | 19    | 19     | 0      | PaymentIntent router (service fully mocked)       |
| tests/unit/test_payment_intent_validation.py   | 14    | 14     | 0      | Service-level validation via mocked UserService   |

**Total: 72 passed, 0 failed**

### Linting

| Tool | Result | Notes             |
|------|--------|-------------------|
| ruff | PASS   | All checks passed |

### Service startup

| Method        | Result  | Notes                                     |
|---------------|---------|-------------------------------------------|
| uvicorn local | OK      | App starts, no import errors              |
| docker compose| blocked | User not in docker group (env limitation) |

### Validation test coverage

| Scenario                                    | Expected | Test |
|---------------------------------------------|----------|------|
| Active merchant, allowed chain+asset        | 201      | ✓    |
| User Service called with correct merchant_id| —        | ✓    |
| Intent + event created when valid           | —        | ✓    |
| Merchant is_active == false                 | 422      | ✓    |
| No DB write when merchant inactive          | —        | ✓    |
| Chain not in allowed_chains                 | 422      | ✓    |
| Allowed non-default chain accepted          | 201      | ✓    |
| Asset not in allowed_assets                 | 422      | ✓    |
| Allowed non-default asset accepted          | 201      | ✓    |
| User Service returns 404                    | 422      | ✓    |
| User Service returns 5xx                    | 503      | ✓    |
| User Service connection refused             | 503      | ✓    |
| User Service timeout                        | 503      | ✓    |
| No DB write when User Service unreachable   | —        | ✓    |

### Known gaps

- No integration tests (require running Postgres + User Service)
- AnalyticsSnapshot endpoints not yet implemented
- Webhook delivery not implemented

### How to run

```bash
pip install fastapi uvicorn sqlalchemy asyncpg psycopg2-binary alembic \
            pydantic pydantic-settings httpx pytest pytest-asyncio ruff

pytest tests/unit -q     # unit tests only
pytest -q                # all tests
ruff check app tests     # lint
```
