# Engineering Summary

**Requirement:** Add optional link expiration TTL in seconds and return 410 Gone when expired.
**Verification:** PASSED; **approval:** interactive.

## Implementation Plan
- T1 — Backward-compatible Expiration Storage (depends on: none); outputs: app/storage.py
- T2 — TTL Service and API Behavior (depends on: T1); outputs: app/service.py, app/main.py
- T3 — TTL Regression Tests and Documentation (depends on: T2); outputs: tests/test_shortener.py, README.md

## Execution
- Wave 1: T1 Backward-compatible Expiration Storage — completed (mock-template)
- Wave 2: T2 TTL Service and API Behavior — completed (mock-template)
- Wave 3: T3 TTL Regression Tests and Documentation — completed (mock-template)

## Generated Artifacts
- `app/storage.py`
- `app/service.py`
- `app/main.py`
- `tests/test_shortener.py`
- `README.md`
- `RISK_AND_VALIDATION.md`
- `execution_trace.json` (written by the CLI)

## Risks, Trade-offs, and Validation
- Risk: The additive SQLite migration must remain compatible with existing URL rows.
- Risk: Expiration timestamps depend on consistent UTC handling.
- Trade-off: TTL is optional; links without expires_at remain active indefinitely.
- Trade-off: An expired link returns 410 and does not count as a successful click.
- Validation: Ruff and pytest, including active, expired, unknown, and legacy-schema migration cases.

## Assumptions and Limitations
- TTL is optional and expressed in positive whole seconds.
- Expiration is evaluated against UTC time; a link is expired at expires_at <= now.
- Links with no TTL remain active indefinitely.
- Expiration is checked before redirect click counts are incremented.
- The local SQLite application is a runnable prototype, not a production scale-out deployment.
- Independent tasks execute concurrently only when their DAG dependencies are satisfied.
- Generated changes require human plan approval; approval does not replace code review.
