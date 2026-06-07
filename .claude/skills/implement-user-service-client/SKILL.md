Implement or fix the internal client used to communicate with User Service.

Steps:
1. Inspect required User Service endpoints and current client code
2. Add the smallest correct client methods
3. Use X-Internal-Secret consistently
4. Add tests with mocked responses
5. Document assumptions

Rules:
- Do not duplicate User Service business logic locally
- Treat User Service as source of truth for merchant config/capabilities
