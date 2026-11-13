# Risk, Tradeoff & Validation Report

**Verification Status:** PASSED (Attempts: 1)

**Plan Approval:** interactive

## 1. Resolved Ambiguities & Assumptions

- TTL is optional and expressed in positive whole seconds.

- Expiration is evaluated against UTC time; a link is expired at expires_at <= now.

- Links with no TTL remain active indefinitely.

- Expiration is checked before redirect click counts are incremented.

## 2. DAG Execution

- Wave 1, T1 (Backward-compatible Expiration Storage): completed via mock-template; artifacts: app/storage.py

- Wave 2, T2 (TTL Service and API Behavior): completed via mock-template; artifacts: app/service.py, app/main.py

- Wave 3, T3 (TTL Regression Tests and Documentation): completed via mock-template; artifacts: tests/test_shortener.py, README.md

## 3. Architectural Tradeoffs

- TTL is optional; links without expires_at remain active indefinitely.

- An expired link returns 410 and does not count as a successful click.

## 4. Identified Risks & Failure Scenarios

- **Risk:** The additive SQLite migration must remain compatible with existing URL rows.

- **Risk:** Expiration timestamps depend on consistent UTC handling.

- **Failure Mode:** Unknown short code -> HTTP 404.

- **Failure Mode:** Expired short code -> HTTP 410.

- **Failure Mode:** Non-positive ttl_seconds -> HTTP 422 through request validation.

## 5. Validation Execution Output

[RUFF EXIT 0]
All checks passed!

[PYTEST EXIT 0]
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.2.0, pluggy-1.7.0 -- C:\Users\prave\Documents\EY\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\prave\Documents\EY\workspace\examples\brownfield-ttl
plugins: anyio-4.16.0, langsmith-0.14.17
collecting ... collected 10 items

tests/test_shortener.py::test_health_check PASSED                        [ 10%]
tests/test_shortener.py::test_shorten_redirect_and_analytics PASSED      [ 20%]
tests/test_shortener.py::test_create_short_url_retries_code_collisions PASSED [ 30%]
tests/test_shortener.py::test_custom_alias_conflict PASSED               [ 40%]
tests/test_shortener.py::test_invalid_url_rejected PASSED                [ 50%]
tests/test_shortener.py::test_ttl_is_optional_and_persisted PASSED       [ 60%]
tests/test_shortener.py::test_non_positive_ttl_is_rejected PASSED        [ 70%]
tests/test_shortener.py::test_expired_link_returns_410_without_incrementing_clicks PASSED [ 80%]
tests/test_shortener.py::test_unknown_link_remains_404 PASSED            [ 90%]
tests/test_shortener.py::test_legacy_database_schema_is_migrated PASSED  [100%]

============================= 10 passed in 0.55s ==============================
