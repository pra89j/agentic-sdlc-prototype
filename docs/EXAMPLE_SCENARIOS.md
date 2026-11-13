# Example Scenarios

## Execution modes

- **Mock mode (`--mock`)** uses deterministic templates for the supported URL-shortener
  prompts below. It runs offline and is useful for repeatable workflow/validation demos;
  its trace reports `mock-template`, so it is not evidence of live model generation.
- **Live mode (omit `--mock`)** uses the configured provider for analysis, planning,
  implementation, and review. It can incur provider usage, and the workflow sends the
  prompt plus relevant workspace source to that provider. Only use it where that sharing
  is permitted.

The mock mode supports this URL-shortener greenfield example, the specific TTL brownfield
enhancement, and the specific ambiguous-sharing example below; it is not a general-purpose
code generator.

For live Gemini runs, create a key in [Google AI Studio](https://aistudio.google.com/api-keys)
and set it in PowerShell. These commands apply only to the current terminal session; do not
put a real key in this repository:

```powershell
$env:LLM_PROVIDER = "gemini"
$env:GEMINI_MODEL = "gemini-4-hydrogen"
$env:GEMINI_API_KEY = "<your-google-ai-studio-api-key>"
```

The mock commands need no key. The Gemini key is for the workflow runner, not for running
the generated URL shortener. Free-tier eligibility depends on the model and project; see
[pricing](https://aistudio.google.com/docs/pricing) and [billing](https://aistudio.google.com/billing).

All examples pause after planning and before any generated file is written. Review the
displayed assumptions, task dependencies, and output paths, then enter `y` to continue.

## 1. Greenfield

**Input**

```text
Build a scalable URL shortener service with APIs, persistence, and analytics.
```

**Representative plan**

| Task | Outputs | Depends on |
|---|---|---|
| Define persistence model and storage adapter | `app/storage.py` | — |
| Implement API and service behavior | `app/main.py`, `app/service.py` | Storage |
| Add integration and unit tests | `tests/` | API/service |
| Document API and scale-out decisions | `README.md`, `docs/URL_SHORTENER_SCALABILITY.md` | API/service |

**Representative outputs**

- `POST /shorten`, `GET /{code}`, `GET /stats/{code}`, and `GET /health`.
- Local evaluation uses SQLite; the scale-out design specifies PostgreSQL for authoritative
  mappings, Redis for redirect caching, and a durable event pipeline for click analytics.
- The final summary records task waves, approval, validation output, risks, assumptions, and
  generated files.

**Validation**

The local demo runs Ruff and pytest. Production-readiness additionally requires load,
failover, queue-backpressure, and database recovery tests; those are not run by this prototype.

## 2. Brownfield

**Input**

```text
Add optional link expiration TTL in seconds and return 410 Gone when expired.
```

**Run**

```powershell
Copy-Item -Recurse workspace\url_shortener workspace\examples\brownfield-ttl-rerun
python run_agent.py --prompt "Add optional link expiration TTL in seconds and return 410 Gone when expired" --workspace workspace\examples\brownfield-ttl-rerun --mock
```

The codebase reasoner scans the copied app and symbols. The approved plan migrates the
SQLite schema, adds TTL handling to service/API behavior, and updates tests and documentation.
Review the assumptions and proposed targets before approving.

**Acceptance checks**

- Expiration is persisted and evaluated against UTC time.
- Expired links return 410; unknown links remain 404.
- Tests cover non-expired, expired, and unknown links, and existing click behavior remains intact.
- Validation runs against the whole target workspace after changes.

The deterministic scenario template applies only to this TTL prompt. It preserves old rows,
checks expiration in UTC, and keeps unknown links distinct from expired ones.

**Live LLM run**

Configure the provider as described in the README, use a fresh copy, and omit `--mock`:

```powershell
Copy-Item -Recurse workspace\url_shortener workspace\examples\brownfield-ttl-live-rerun
python run_agent.py --prompt "Add optional link expiration TTL in seconds and return 410 Gone when expired" --workspace workspace\examples\brownfield-ttl-live-rerun
```

Review the model-generated impact analysis and plan, then approve it. A completed live run
must have `mock_mode: false` and `llm-task-agent` executors in
`workspace\examples\brownfield-ttl-live-rerun\execution_trace.json`; validate its report and
tests before calling it successful.

**Recorded mock result**

The run in `workspace\examples\brownfield-ttl` completed with validation passed:
Ruff passed and all 10 tests passed, including expired/unknown link behavior and migration
from the legacy SQLite schema. Its trace correctly records `mock_mode: true`.

## 3. Ambiguous requirement

**Input**

```text
Make links easier to share.
```

**Run**

```powershell
Copy-Item -Recurse workspace\url_shortener workspace\examples\ambiguous-sharing-rerun
python run_agent.py --prompt "Make links easier to share." --workspace workspace\examples\ambiguous-sharing-rerun --mock
```

**Assumptions and resolution**

The mock analyst explicitly treats the request as asking for memorable custom aliases,
keeps HTTP(S)-only URLs, no expiration by default, and aggregate click counts, and does not
assume a frontend, QR code, or social integration. The existing app already supports
optional aliases, so the plan documents the evidence and asks for clarification before
building a different sharing workflow.

This is a brownfield analysis, not a claim that a sharing UI was implemented. The approval
gate displays the assumptions before the documentation-only task runs. Rejecting the plan
records the decision and stops before writing application files.

The generated `docs/AMBIGUOUS_REQUIREMENT.md`, engineering summary, risk report, and
`execution_trace.json` record the interpretation and validation result.

**Live Gemini run**

Use a fresh copy and omit `--mock`:

```powershell
Copy-Item -Recurse workspace\url_shortener workspace\examples\ambiguous-sharing-live-rerun
python run_agent.py --prompt "Make links easier to share." --workspace workspace\examples\ambiguous-sharing-live-rerun
```

Review the model's normalized requirement and assumptions before approval. The current
workflow provides a plan-approval gate, not a separate multi-turn clarification dialogue;
reject the plan if its interpretation is not acceptable. Do not treat a live run as
validated unless its trace has `mock_mode: false` and its own validation passed.

**Recorded live result**

The successful user-run used `gemini-4-hydrogen` and completed the approved five-task,
four-wave plan. Its trace records `mock_mode: false`, `llm-task-agent` executors, and
`validation_passed: true`; the workflow reported Ruff passing and 37 tests passing.

Post-run review found that the generated requirements file omitted the app's original
runtime dependencies and the README did not describe the new endpoints. Both were updated.
Review also removed duplicated handwritten QR encoders and fake QR test scaffolding in favor
of the declared `segno` dependency. The app was independently rerun afterward: 37 tests
passed and Ruff passed. See the live workspace's `ENGINEERING_SUMMARY.md` and
`RISK_AND_VALIDATION.md` for the reviewed output and remaining prototype limitations.

**Recorded mock result**

The mock run in `workspace\examples\ambiguous-sharing` completed with validation passed:
Ruff passed and all 5 existing tests passed. It documents the alias-based assumption and
does not claim to implement a sharing UI. Its trace correctly records `mock_mode: true`.
The separate live result is in `workspace\examples\ambiguous-sharing-live`.
