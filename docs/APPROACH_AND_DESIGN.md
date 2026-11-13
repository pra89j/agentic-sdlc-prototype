# Approach, Architecture & Design Tradeoffs

## 1. Problem Approach
Rather than wrapping a single LLM prompt to emit code, this prototype models the Software Development Life Cycle (SDLC) as a **stateful, cyclic state machine** built with **LangGraph** and **Pydantic**. Every stage produces an inspectable artifact. A human must approve the dependency plan before writes are allowed; generated output is then verified by `ruff` and `pytest`.

## 2. Core Capabilities & Implementation Details
- **Requirement Understanding (`analyst_node`):** Classifies greenfield vs. brownfield intent based on workspace state, normalizes vague requests into functional/non-functional specifications, and logs explicit assumptions for underspecified details.
- **Brownfield Codebase Reasoning (`reasoner_node`):** Uses Python's `ast` module and workspace file scanning to extract existing classes, functions, and module boundaries so enhancements integrate cleanly without breaking existing contracts.
- **Task Decomposition (`planner_node`):** Produces a `TaskDAG` separating storage, API/service, tests, and documentation. The DAG is validated before approval; live plans with invalid dependencies, duplicate output paths, or cycles receive up to two repair attempts and fail closed before writes if still invalid.
- **Human Oversight (`approval_node`):** Prints dependencies and target files and waits for an explicit approval before code generation. Non-interactive approval requires the explicit `--approve-plan` flag.
- **DAG Orchestration (`executor_node`):** Schedules ready tasks in dependency waves. Independent tasks run concurrently as separate task-agent calls; completed artifacts are written only to their declared target paths. The trace records each task, wave, and output.
- **Self-Healing Validation (`validator_node`):** Runs Ruff plus unit and integration tests. On failure, validation output is sent to the task agents for up to 3 bounded attempts.
- **Risk & Tradeoff Governance (`critic_node`):** Writes `RISK_AND_VALIDATION.md` and `ENGINEERING_SUMMARY.md`; the CLI writes the full `execution_trace.json`.
- **Model Providers (`_get_llm`):** Supports OpenAI by default and Google Gemini through `LLM_PROVIDER=gemini`; provider credentials are read from environment variables, never stored in generated artifacts.

## 3. Key Assumptions & Tradeoffs

| Dimension | Prototype Choice | Tradeoff & Production Evolution |
| :--- | :--- | :--- |
| **Workflow Control** | Human-approved DAG, dependency waves, parallel ready tasks, bounded retry cycles (max 3). | Trades open-ended autonomy for predictable execution, auditability, and bounded latency/cost. |
| **Codebase Indexing** | Python AST symbol extraction + targeted file reading. | Zero embedding overhead and fast execution on small/medium services; would pair with semantic vector + call-graph indexing for large monorepos. |
| **Target App Storage** | SQLite (`sqlite3` standard library) in the URL shortener demo. | Keeps setup simple and makes the sample easy to run locally. PostgreSQL, Redis, and asynchronous analytics are optional future evolution ideas, not requirements for this prototype. |
| **Redirect Semantics** | HTTP `307 Temporary Redirect` for `GET /{code}`. | Prevents aggressive browser/CDN caching from bypassing click-tracking telemetry, trading slight edge latency for accurate analytics. |
| **Execution Sandbox** | Local subprocess validation with timeout limits. | Simple and portable for a local prototype; it is not a security sandbox. Production requires ephemeral containers or microVMs, least-privilege credentials, and network/filesystem isolation for untrusted generated code. |

## 4. Limitations
- The `--mock` mode is a deterministic URL-shortener reference template, not a general code generator. Live planning and per-task generation require an LLM API key, supplied through `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) in the shell environment, never a checked-in file.
- The live ambiguous-sharing example was run with the Gemini Developer API model `gemini-4-hydrogen`; its workspace trace records `mock_mode: false` and passed validation. Model availability, free-tier eligibility, and quotas can change. Check [Gemini API pricing](https://aistudio.google.com/docs/pricing) and [billing status](https://aistudio.google.com/billing). Review provider data terms before sending source code; free-tier prompts may be used to improve provider products.
- The mock DAG includes independent test and documentation tasks to demonstrate ready-task concurrency. Live plans may expose other dependency waves.
- Plan approval is a human gate, not a substitute for source review or deployment approval.
- The application generated for local evaluation uses SQLite and synchronous click increments. See [URL_SHORTENER_SCALABILITY.md](./URL_SHORTENER_SCALABILITY.md) for optional future evolution; load and failover tests are not expected or claimed for this demo.
