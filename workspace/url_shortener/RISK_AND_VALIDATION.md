# Risk, Tradeoff & Validation Report

**Verification Status:** PASSED (Attempts: 1)

**Plan Approval:** command-line

## 1. Resolved Ambiguities & Assumptions

- Storage unspecified -> Selected SQLite (url_shortener.db) for runnable local demo

- Short code length unspecified -> Selected 6-char random alphanumeric ID with collision retry

- Redirect HTTP status unspecified -> Selected 307 Temporary Redirect for accurate analytics

## 2. DAG Execution

- Wave 1, T1 (Storage Layer): completed via mock-template; artifacts: app/storage.py

- Wave 2, T2 (API & Service): completed via mock-template; artifacts: app/service.py, app/main.py, requirements.txt

- Wave 3, T3 (Tests & Docs): completed via mock-template; artifacts: tests/test_shortener.py, README.md

- Wave 3, T4 (Scale-out Design): completed via mock-template; artifacts: docs/URL_SHORTENER_SCALABILITY.md

## 3. Architectural Tradeoffs

- SQLite is retained for zero-setup local execution; optional future evolution could use PostgreSQL, Redis, and an asynchronous event pipeline.

- HTTP 307 is used to avoid permanent redirect caching bypassing click tracking.

## 4. Identified Risks & Failure Scenarios

- **Risk:** SQLite is a single-node local-demo store and is not the scale-out persistence tier.

- **Risk:** Short-code collisions become more likely as the keyspace grows; the database uniqueness constraint and retry loop are required.

- **Risk:** Click counts in the local demo are synchronously updated and can contend under load.

- **Failure Mode:** Invalid URL -> HTTP 422 via Pydantic.

- **Failure Mode:** Unknown code -> HTTP 404.

## 5. Validation Execution Output

[RUFF EXIT 0]
All checks passed!

[PYTEST EXIT 0]
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.2.0, pluggy-1.7.0 -- C:\Users\prave\Documents\EY\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\prave\Documents\EY\workspace\url_shortener
plugins: anyio-4.16.0, langsmith-0.14.17
collecting ... collected 5 items

tests/test_shortener.py::test_health_check PASSED                        [ 20%]
tests/test_shortener.py::test_shorten_redirect_and_analytics PASSED      [ 40%]
tests/test_shortener.py::test_create_short_url_retries_code_collisions PASSED [ 60%]
tests/test_shortener.py::test_custom_alias_conflict PASSED               [ 80%]
tests/test_shortener.py::test_invalid_url_rejected PASSED                [100%]

============================== 5 passed in 0.41s ==============================
