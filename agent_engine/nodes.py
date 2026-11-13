import os
import textwrap
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TypedDict
from langchain_openai import ChatOpenAI
from agent_engine.schemas import CodebaseImpact, CodeBundle, EngineeringSpec, RiskReport, TaskDAG
from agent_engine.tools import (
    read_workspace_files,
    run_validation_suite,
    scan_workspace,
    task_execution_waves,
    write_files,
)


class SDLCState(TypedDict):
    requirement: str
    workspace_path: str
    mock_mode: bool
    spec: dict
    impact: dict
    task_dag: dict
    code_bundle: dict
    validation_passed: bool
    validation_logs: str
    retry_count: int
    risk_report: dict
    auto_approve: bool
    approved: bool
    approval_source: str
    execution_log: list[dict]
    workflow_status: str


MAX_DAG_PLANNING_ATTEMPTS = 3


def _mock_scenario(requirement: str) -> str:
    normalized = requirement.casefold()
    if "ttl" in normalized and "410" in normalized:
        return "brownfield_ttl"
    if "easier to share" in normalized:
        return "ambiguous_sharing"
    return "url_shortener"


def _validate_task_dag(dag: TaskDAG) -> dict:
    dag_data = dag.model_dump()
    task_execution_waves(dag_data["tasks"], dag_data["execution_order"])
    return dag_data


def _generate_validated_task_dag(llm, prompt: str) -> dict:
    validation_error = ""
    for attempt in range(1, MAX_DAG_PLANNING_ATTEMPTS + 1):
        repair_prompt = ""
        if validation_error:
            repair_prompt = (
                "\nThe previous DAG failed structural validation: "
                f"{validation_error}\nReturn a corrected complete DAG. Every target file "
                "must be assigned to exactly one task; dependencies must be valid and "
                "execution_order must be topologically sorted."
            )
            print(
                f"      -> Planner DAG invalid; requesting correction "
                f"({attempt}/{MAX_DAG_PLANNING_ATTEMPTS})..."
            )
        dag = llm.invoke(prompt + repair_prompt)
        try:
            return _validate_task_dag(dag)
        except ValueError as exc:
            validation_error = str(exc)

    raise ValueError(
        "Planner could not produce a valid task DAG after "
        f"{MAX_DAG_PLANNING_ATTEMPTS} attempts: {validation_error}"
    )


def _get_llm():
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    if provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Gemini provider selected but no GEMINI_API_KEY or GOOGLE_API_KEY is set."
            )
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
            api_key=api_key,
            temperature=0.1,
            request_timeout=60,
            retries=1,
        )
    if provider == "openai":
        return ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.1,
            timeout=60,
            max_retries=1,
        )
    raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")


def analyst_node(state: SDLCState) -> dict:
    print("\n[1/7] Requirement Analyst: Interpreting intent & resolving ambiguities...")
    scan = scan_workspace(Path(state["workspace_path"]))
    inferred_mode = "greenfield" if scan["is_empty"] else "brownfield"

    if state["mock_mode"]:
        scenario = _mock_scenario(state["requirement"])
        if scenario == "brownfield_ttl":
            spec = EngineeringSpec(
                mode=inferred_mode,
                problem_statement=(
                    "Add optional link expiration TTL in seconds and return 410 Gone "
                    "when expired."
                ),
                functional_requirements=[
                    "POST /shorten accepts an optional positive ttl_seconds value.",
                    "Persist expiration timestamps in UTC; links without a TTL never expire.",
                    "Expired links return HTTP 410 without incrementing click analytics.",
                    "Unknown links continue to return HTTP 404.",
                    "Existing link creation, redirects, aliases, and analytics remain compatible.",
                ],
                non_functional_requirements=[
                    "Migrate existing SQLite databases without losing URL mappings or click counts.",
                    "Validate the expiration behavior with deterministic API tests.",
                ],
                ambiguities_resolved=[
                    "TTL is optional and expressed in positive whole seconds.",
                    "Expiration is evaluated against UTC time; a link is expired at expires_at <= now.",
                    "Links with no TTL remain active indefinitely.",
                    "Expiration is checked before redirect click counts are incremented.",
                ],
            )
            return {"spec": spec.model_dump()}
        if scenario == "ambiguous_sharing":
            spec = EngineeringSpec(
                mode=inferred_mode,
                problem_statement=(
                    "Evaluate the vague request to make links easier to share, using "
                    "memorable custom aliases as the initial interpretation."
                ),
                functional_requirements=[
                    "Verify whether the existing optional custom_alias API meets the assumed sharing need.",
                    "Document the interpretation, alternatives, and evidence before expanding scope.",
                ],
                non_functional_requirements=[
                    "Do not add a frontend, QR codes, or social integrations without clarification.",
                    "Preserve existing URL validation and aggregate click analytics.",
                ],
                ambiguities_resolved=[
                    "Interpret 'easier to share' as memorable custom aliases, not a new sharing UI.",
                    "Keep HTTP(S)-only URL validation, no expiration by default, and aggregate click counts.",
                    "The existing API already supports aliases; verify and document it instead of duplicating behavior.",
                    "Ask for clarification before implementing a copy button, QR codes, or social integrations.",
                ],
            )
            return {"spec": spec.model_dump()}
        spec = EngineeringSpec(
            mode=inferred_mode,
            problem_statement=f"Implement URL Shortener capability: {state['requirement']}",
            functional_requirements=[
                "POST /shorten accepts long URL and returns unique Base62 short code",
                "GET /{code} redirects (307) to original URL and increments click counter",
                "GET /stats/{code} returns metadata, creation timestamp, and click count",
                "GET /health returns service status",
            ],
            non_functional_requirements=[
                "Persist URL mappings in local SQLite database for zero-setup portability",
                "Validate URLs using Pydantic HttpUrl to prevent malformed redirects",
            ],
            ambiguities_resolved=[
                "Storage unspecified -> Selected SQLite (url_shortener.db) for runnable local demo",
                "Short code length unspecified -> Selected 6-char random alphanumeric ID with collision retry",
                "Redirect HTTP status unspecified -> Selected 307 Temporary Redirect for accurate analytics",
            ],
        )
        return {"spec": spec.model_dump()}

    llm = _get_llm().with_structured_output(EngineeringSpec)
    prompt = (
        f"Analyze requirement: '{state['requirement']}'. Workspace mode: {inferred_mode}, "
        f"files: {scan['files']}. Normalize into EngineeringSpec with explicit ambiguities_resolved."
    )
    return {"spec": llm.invoke(prompt).model_dump()}


def reasoner_node(state: SDLCState) -> dict:
    print("[2/7] Codebase Reasoner: Mapping architecture & impact...")
    workspace = Path(state["workspace_path"])
    scan = scan_workspace(workspace)

    if scan["is_empty"]:
        impact = CodebaseImpact(
            existing_files=[],
            impacted_modules=["app/main.py", "app/storage.py", "app/service.py"],
            data_flow_summary="Greenfield repository: FastAPI -> Service -> SQLite.",
            integration_risks=["Ensure SQLite thread safety across FastAPI request workers."],
        )
        return {"impact": impact.model_dump()}

    if state["mock_mode"]:
        scenario = _mock_scenario(state["requirement"])
        if scenario == "brownfield_ttl":
            impact = CodebaseImpact(
                existing_files=scan["files"],
                impacted_modules=[
                    "app/storage.py",
                    "app/service.py",
                    "app/main.py",
                    "tests/test_shortener.py",
                    "README.md",
                ],
                data_flow_summary=(
                    "Brownfield change to the existing FastAPI -> service -> SQLite path; "
                    "a backward-compatible schema migration adds expires_at."
                ),
                integration_risks=[
                    "Existing SQLite files need an additive migration that preserves rows.",
                    "Expired links must not increment clicks or be confused with unknown codes.",
                ],
            )
            return {"impact": impact.model_dump()}
        if scenario == "ambiguous_sharing":
            impact = CodebaseImpact(
                existing_files=scan["files"],
                impacted_modules=["app/main.py", "app/service.py", "tests/test_shortener.py"],
                data_flow_summary=(
                    "The existing POST /shorten route already accepts optional custom aliases; "
                    "the narrow interpretation needs documentation, not duplicate code."
                ),
                integration_risks=[
                    "The vague request could instead mean a client-side copy/QR/share feature; "
                    "do not claim those behaviors without clarification."
                ],
            )
            return {"impact": impact.model_dump()}
        impact = CodebaseImpact(
            existing_files=scan["files"],
            impacted_modules=scan["files"],
            data_flow_summary="Brownfield enhancement: extending existing FastAPI routes and SQLite schema.",
            integration_risks=["Maintain backward compatibility with existing SQLite columns."],
        )
        return {"impact": impact.model_dump()}

    llm = _get_llm().with_structured_output(CodebaseImpact)
    prompt = f"Analyze codebase for: {state['spec']['problem_statement']}\nSymbols: {scan['symbols']}\n{read_workspace_files(workspace)}"
    return {"impact": llm.invoke(prompt).model_dump()}


def planner_node(state: SDLCState) -> dict:
    print("[3/7] Task Architect: Decomposing into dependency DAG...")
    if state["mock_mode"]:
        scenario = _mock_scenario(state["requirement"])
        if scenario == "brownfield_ttl":
            dag = TaskDAG(
                tasks=[
                    {
                        "id": "T1",
                        "title": "Backward-compatible Expiration Storage",
                        "category": "contract",
                        "dependencies": [],
                        "target_files": ["app/storage.py"],
                        "acceptance_criteria": (
                            "Persist expires_at and migrate existing SQLite tables "
                            "without losing rows."
                        ),
                    },
                    {
                        "id": "T2",
                        "title": "TTL Service and API Behavior",
                        "category": "implementation",
                        "dependencies": ["T1"],
                        "target_files": ["app/service.py", "app/main.py"],
                        "acceptance_criteria": (
                            "Accept positive optional ttl_seconds; return 410 for expired "
                            "links, 404 for unknown links, and preserve analytics behavior."
                        ),
                    },
                    {
                        "id": "T3",
                        "title": "TTL Regression Tests and Documentation",
                        "category": "test",
                        "dependencies": ["T2"],
                        "target_files": ["tests/test_shortener.py", "README.md"],
                        "acceptance_criteria": (
                            "Test active, expired, unknown, and legacy-schema cases; "
                            "document the optional TTL API."
                        ),
                    },
                ],
                execution_order=["T1", "T2", "T3"],
            )
            return {"task_dag": _validate_task_dag(dag)}
        if scenario == "ambiguous_sharing":
            dag = TaskDAG(
                tasks=[
                    {
                        "id": "T1",
                        "title": "Document Ambiguous Requirement Resolution",
                        "category": "documentation",
                        "dependencies": [],
                        "target_files": ["docs/AMBIGUOUS_REQUIREMENT.md"],
                        "acceptance_criteria": (
                            "Record assumptions, existing alias evidence, unimplemented "
                            "alternatives, and the clarification needed before expanding scope."
                        ),
                    }
                ],
                execution_order=["T1"],
            )
            return {"task_dag": _validate_task_dag(dag)}
        dag = TaskDAG(
            tasks=[
                {"id": "T1", "title": "Storage Layer", "category": "contract", "dependencies": [], "target_files": ["app/storage.py"], "acceptance_criteria": "SQLite schema and CRUD."},
                {"id": "T2", "title": "API & Service", "category": "implementation", "dependencies": ["T1"], "target_files": ["app/service.py", "app/main.py", "requirements.txt"], "acceptance_criteria": "Endpoints working with documented installable dependencies."},
                {"id": "T3", "title": "Tests & Docs", "category": "test", "dependencies": ["T2"], "target_files": ["tests/test_shortener.py", "README.md"], "acceptance_criteria": "Pytest and ruff pass."},
                {"id": "T4", "title": "Scale-out Design", "category": "documentation", "dependencies": ["T2"], "target_files": ["docs/URL_SHORTENER_SCALABILITY.md"], "acceptance_criteria": "Document scale-out architecture, trade-offs, and migration path."},
            ],
            execution_order=["T1", "T2", "T3", "T4"],
        )
        return {"task_dag": _validate_task_dag(dag)}

    llm = _get_llm().with_structured_output(TaskDAG)
    prompt = (
        f"Create TaskDAG for spec: {state['spec']} and impact: {state['impact']}\n"
        "Every target file must be assigned to exactly one task. Dependencies must "
        "reference valid task IDs, contain no cycles, and execution_order must be "
        "topologically sorted."
    )
    return {"task_dag": _generate_validated_task_dag(llm, prompt)}


def approval_node(state: SDLCState) -> dict:
    tasks = state["task_dag"]["tasks"]
    print("\nPlan Approval: review the proposed tasks before any generated files are written.")
    assumptions = state["spec"]["ambiguities_resolved"]
    if assumptions:
        print("  Assumptions:")
        for assumption in assumptions:
            print(f"    - {assumption}")
    for task in tasks:
        dependencies = ", ".join(task["dependencies"]) or "none"
        targets = ", ".join(task["target_files"])
        print(f"  {task['id']} {task['title']} (depends on: {dependencies})")
        print(f"     outputs: {targets}")

    if state["auto_approve"]:
        print("Plan approved via --approve-plan.")
        return {
            "approved": True,
            "approval_source": "command-line",
            "workflow_status": "plan_approved",
        }

    try:
        answer = input("Approve this plan and allow code generation? [y/N]: ").strip().lower()
    except EOFError as exc:
        raise RuntimeError(
            "Plan approval requires an interactive terminal; rerun with --approve-plan "
            "only after reviewing the printed plan."
        ) from exc

    approved = answer in {"y", "yes"}
    print("Plan approved." if approved else "Plan rejected; no files were generated.")
    return {
        "approved": approved,
        "approval_source": "interactive" if approved else "rejected",
        "workflow_status": "plan_approved" if approved else "plan_rejected",
    }


def approval_route(state: SDLCState) -> str:
    return "execute" if state["approved"] else "stop"


def executor_node(state: SDLCState) -> dict:
    attempt = state.get("retry_count", 0) + 1
    print(f"[4/7] DAG Execution (Attempt {attempt}): Running ready tasks by dependency wave...")
    workspace = Path(state["workspace_path"])
    retry_note = ""
    if state.get("validation_logs") and not state.get("validation_passed", True):
        retry_note = f"\nFix these validation errors:\n{state['validation_logs']}\n"
    waves = task_execution_waves(
        state["task_dag"]["tasks"], state["task_dag"]["execution_order"]
    )
    reference_bundle = _build_reference_shortener_bundle() if state["mock_mode"] else None
    scenario = _mock_scenario(state["requirement"]) if state["mock_mode"] else ""
    if scenario == "brownfield_ttl":
        reference_bundle = _build_brownfield_ttl_bundle()
    elif scenario == "ambiguous_sharing":
        reference_bundle = _build_ambiguous_sharing_bundle()
    reference_files = (
        {item.path: item.content for item in reference_bundle.files}
        if reference_bundle
        else {}
    )
    generated_files = []
    execution_log = list(state.get("execution_log", []))

    for wave_number, wave in enumerate(waves, start=1):
        workspace_context = read_workspace_files(workspace)

        def execute_task(task: dict) -> tuple[dict, list[dict]]:
            targets = task["target_files"]
            if state["mock_mode"]:
                missing = [target for target in targets if target not in reference_files]
                if missing:
                    raise ValueError(
                        f"Mock template has no output for task {task['id']}: {missing}"
                    )
                files = [
                    {"path": target, "content": reference_files[target]}
                    for target in targets
                ]
                return task, files

            prompt = (
                "Act as an independent implementation task agent. Generate only the complete "
                f"files assigned to task {task['id']} ({task['title']}).\n"
                f"Requirement: {state['spec']}\n"
                f"Codebase impact: {state['impact']}\n"
                f"Task and acceptance criteria: {task}\n"
                f"Dependency DAG: {state['task_dag']}\n"
                f"Existing workspace files:\n{workspace_context}\n"
                f"Validation feedback from the previous attempt:\n{retry_note}\n"
                f"Return exactly these paths and no others: {targets}"
            )
            bundle = _get_llm().with_structured_output(CodeBundle).invoke(prompt)
            files = [item.model_dump() for item in bundle.files]
            actual_paths = {item["path"] for item in files}
            if actual_paths != set(targets) or len(files) != len(actual_paths):
                raise ValueError(
                    f"Task {task['id']} returned paths {sorted(actual_paths)}; "
                    f"expected exactly {sorted(targets)}"
                )
            return task, files

        with ThreadPoolExecutor(max_workers=max(1, len(wave))) as pool:
            results = list(pool.map(execute_task, wave))

        for task, files in results:
            write_files(workspace, files)
            generated_files.extend(files)
            execution_log.append(
                {
                    "attempt": attempt,
                    "wave": wave_number,
                    "task_id": task["id"],
                    "title": task["title"],
                    "status": "completed",
                    "executor": "mock-template" if state["mock_mode"] else "llm-task-agent",
                    "artifacts": [item["path"] for item in files],
                }
            )
            print(f"      -> Wave {wave_number}: completed {task['id']} ({task['title']})")

    bundle = CodeBundle(
        files=generated_files,
        api_contract_summary="POST /shorten, GET /{code}, GET /stats/{code}, GET /health",
        architecture_notes=(
            "Dependency-wave task execution; runnable local FastAPI and SQLite demo, "
            "with scale-out architecture documented separately."
        ),
    )
    return {
        "code_bundle": bundle.model_dump(),
        "retry_count": attempt,
        "execution_log": execution_log,
    }


def validator_node(state: SDLCState) -> dict:
    print("[5/7] Validation Gate: Running ruff linter and pytest suite...")
    passed, logs = run_validation_suite(Path(state["workspace_path"]))
    print("      -> Validation " + ("PASSED" if passed else "FAILED"))
    return {
        "validation_passed": passed,
        "validation_logs": logs,
        "workflow_status": "validated" if passed else "validation_failed",
    }


def critic_node(state: SDLCState) -> dict:
    print("[6/7] Critic & Risk Gate: Generating review reports...")
    workspace = Path(state["workspace_path"])

    if state["mock_mode"]:
        scenario = _mock_scenario(state["requirement"])
        if scenario == "brownfield_ttl":
            report = RiskReport(
                technical_risks=[
                    "The additive SQLite migration must remain compatible with existing URL rows.",
                    "Expiration timestamps depend on consistent UTC handling.",
                ],
                tradeoffs_made=[
                    "TTL is optional; links without expires_at remain active indefinitely.",
                    "An expired link returns 410 and does not count as a successful click.",
                ],
                failure_scenarios=[
                    "Unknown short code -> HTTP 404.",
                    "Expired short code -> HTTP 410.",
                    "Non-positive ttl_seconds -> HTTP 422 through request validation.",
                ],
                validation_strategy=(
                    "Ruff and pytest, including active, expired, unknown, and legacy-schema "
                    "migration cases."
                ),
                verification_status="PASSED" if state["validation_passed"] else "FAILED",
            )
        elif scenario == "ambiguous_sharing":
            report = RiskReport(
                technical_risks=[
                    "The request may mean a copy button, QR code, or social sharing, none of "
                    "which is implemented by this alias-focused interpretation.",
                ],
                tradeoffs_made=[
                    "Reused the existing optional custom-alias feature rather than duplicating it.",
                    "Made no application-code changes; the run documents the assumption and evidence.",
                ],
                failure_scenarios=[
                    "If the user intended a sharing UI or QR code, clarify that scope before implementation."
                ],
                validation_strategy=(
                    "Ruff and pytest regression suite for the existing API; verify the existing "
                    "custom-alias endpoint and conflict behavior."
                ),
                verification_status="PASSED" if state["validation_passed"] else "FAILED",
            )
        else:
            report = RiskReport(
                technical_risks=[
                    "SQLite is a single-node local-demo store and is not the scale-out persistence tier.",
                    "Short-code collisions become more likely as the keyspace grows; the database uniqueness constraint and retry loop are required.",
                    "Click counts in the local demo are synchronously updated and can contend under load.",
                ],
                tradeoffs_made=[
                    "SQLite is retained for zero-setup local execution; optional future evolution could use PostgreSQL, Redis, and an asynchronous event pipeline.",
                    "HTTP 307 is used to avoid permanent redirect caching bypassing click tracking.",
                ],
                failure_scenarios=["Invalid URL -> HTTP 422 via Pydantic.", "Unknown code -> HTTP 404."],
                validation_strategy=(
                    "Ruff static analysis + pytest service unit tests and FastAPI TestClient "
                    "integration tests."
                ),
                verification_status="PASSED" if state["validation_passed"] else "FAILED",
            )
    else:
        llm = _get_llm().with_structured_output(RiskReport)
        report = llm.invoke(f"Review implementation for spec: {state['spec']}. Logs:\n{state['validation_logs']}")

    lines = [
        "# Risk, Tradeoff & Validation Report",
        f"**Verification Status:** {report.verification_status} (Attempts: {state['retry_count']})",
        f"**Plan Approval:** {state['approval_source']}",
        "## 1. Resolved Ambiguities & Assumptions",
        *[f"- {a}" for a in state["spec"]["ambiguities_resolved"]],
        "## 2. DAG Execution",
        *[
            f"- Wave {entry['wave']}, {entry['task_id']} ({entry['title']}): "
            f"{entry['status']} via {entry['executor']}; artifacts: {', '.join(entry['artifacts'])}"
            for entry in state["execution_log"]
        ],
        "## 3. Architectural Tradeoffs",
        *[f"- {t}" for t in report.tradeoffs_made],
        "## 4. Identified Risks & Failure Scenarios",
        *[f"- **Risk:** {r}" for r in report.technical_risks],
        *[f"- **Failure Mode:** {f}" for f in report.failure_scenarios],
        "## 5. Validation Execution Output",
        state["validation_logs"],
    ]
    (workspace / "RISK_AND_VALIDATION.md").write_text("\n\n".join(lines) + "\n", encoding="utf-8")
    summary = [
        "# Engineering Summary",
        "",
        f"**Requirement:** {state['spec']['problem_statement']}",
        f"**Verification:** {report.verification_status}; **approval:** {state['approval_source']}.",
        "",
        "## Implementation Plan",
        *[
            f"- {task['id']} — {task['title']} (depends on: "
            f"{', '.join(task['dependencies']) or 'none'}); outputs: "
            f"{', '.join(task['target_files'])}"
            for task in state["task_dag"]["tasks"]
        ],
        "",
        "## Execution",
        *[
            f"- Wave {entry['wave']}: {entry['task_id']} {entry['title']} — "
            f"{entry['status']} ({entry['executor']})"
            for entry in state["execution_log"]
        ],
        "",
        "## Generated Artifacts",
        *[f"- `{item['path']}`" for item in state["code_bundle"]["files"]],
        "- `RISK_AND_VALIDATION.md`",
        "- `execution_trace.json` (written by the CLI)",
        "",
        "## Risks, Trade-offs, and Validation",
        *[f"- Risk: {risk}" for risk in report.technical_risks],
        *[f"- Trade-off: {tradeoff}" for tradeoff in report.tradeoffs_made],
        f"- Validation: {report.validation_strategy}",
        "",
        "## Assumptions and Limitations",
        *[f"- {item}" for item in state["spec"]["ambiguities_resolved"]],
        "- The local SQLite application is a runnable prototype, not a production scale-out deployment.",
        "- Independent tasks execute concurrently only when their DAG dependencies are satisfied.",
        "- Generated changes require human plan approval; approval does not replace code review.",
    ]
    (workspace / "ENGINEERING_SUMMARY.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print("[7/7] Engineering Summary: Wrote ENGINEERING_SUMMARY.md.")
    return {"risk_report": report.model_dump()}


def _build_reference_shortener_bundle() -> CodeBundle:
    storage_lines = [
        "import os",
        "import sqlite3",
        "from datetime import datetime, timezone",
        "",
        "def get_db_path() -> str:",
        "    return os.getenv('SHORTENER_DB_PATH', 'url_shortener.db')",
        "",
        "def init_db() -> None:",
        "    with sqlite3.connect(get_db_path()) as conn:",
        "        conn.execute('CREATE TABLE IF NOT EXISTS urls (code TEXT PRIMARY KEY, original_url TEXT NOT NULL, created_at TEXT NOT NULL, clicks INTEGER NOT NULL DEFAULT 0)')",
        "        conn.commit()",
        "",
        "def save_url(code: str, original_url: str) -> bool:",
        "    init_db()",
        "    try:",
        "        with sqlite3.connect(get_db_path()) as conn:",
        "            conn.execute('INSERT INTO urls (code, original_url, created_at, clicks) VALUES (?, ?, ?, 0)', (code, original_url, datetime.now(timezone.utc).isoformat()))",
        "            conn.commit()",
        "        return True",
        "    except sqlite3.IntegrityError:",
        "        return False",
        "",
        "def get_url_and_increment(code: str) -> str | None:",
        "    init_db()",
        "    with sqlite3.connect(get_db_path()) as conn:",
        "        row = conn.execute('SELECT original_url FROM urls WHERE code = ?', (code,)).fetchone()",
        "        if not row:",
        "            return None",
        "        conn.execute('UPDATE urls SET clicks = clicks + 1 WHERE code = ?', (code,))",
        "        conn.commit()",
        "        return row[0]",
        "",
        "def get_stats(code: str) -> dict | None:",
        "    init_db()",
        "    with sqlite3.connect(get_db_path()) as conn:",
        "        row = conn.execute('SELECT code, original_url, created_at, clicks FROM urls WHERE code = ?', (code,)).fetchone()",
        "        if not row:",
        "            return None",
        "        return {'code': row[0], 'original_url': row[1], 'created_at': row[2], 'clicks': row[3]}",
    ]

    service_lines = [
        "import secrets",
        "import string",
        "from app.storage import get_stats, get_url_and_increment, save_url",
        "",
        "ALPHABET = string.ascii_letters + string.digits",
        "",
        "def generate_code(length: int = 6) -> str:",
        "    return ''.join(secrets.choice(ALPHABET) for _ in range(length))",
        "",
        "def create_short_url(original_url: str, custom_alias: str | None = None) -> str:",
        "    if custom_alias:",
        "        if not save_url(custom_alias, original_url):",
        "            raise ValueError('Custom alias already exists.')",
        "        return custom_alias",
        "    for _ in range(5):",
        "        code = generate_code()",
        "        if save_url(code, original_url):",
        "            return code",
        "    raise RuntimeError('Failed to generate unique short code.')",
        "",
        "def resolve_short_url(code: str) -> str | None:",
        "    return get_url_and_increment(code)",
        "",
        "def fetch_url_stats(code: str) -> dict | None:",
        "    return get_stats(code)",
    ]

    main_lines = [
        "from contextlib import asynccontextmanager",
        "from fastapi import FastAPI, HTTPException, Request",
        "from fastapi.responses import RedirectResponse",
        "from pydantic import BaseModel, Field, HttpUrl",
        "from app.service import create_short_url, fetch_url_stats, resolve_short_url",
        "from app.storage import init_db",
        "",
        "@asynccontextmanager",
        "async def lifespan(app: FastAPI):",
        "    init_db()",
        "    yield",
        "",
        "app = FastAPI(title='Agent-Generated URL Shortener', version='1.0.0', lifespan=lifespan)",
        "",
        "class ShortenRequest(BaseModel):",
        "    url: HttpUrl",
        "    custom_alias: str | None = Field(default=None, min_length=3, max_length=20, pattern='^[a-zA-Z0-9_-]+$')",
        "",
        "class ShortenResponse(BaseModel):",
        "    code: str",
        "    short_url: str",
        "    original_url: str",
        "",
        "@app.get('/health')",
        "def health() -> dict:",
        "    return {'status': 'ok'}",
        "",
        "@app.post('/shorten', response_model=ShortenResponse, status_code=201)",
        "def shorten_url(payload: ShortenRequest, request: Request) -> ShortenResponse:",
        "    try:",
        "        code = create_short_url(str(payload.url), payload.custom_alias)",
        "    except ValueError as exc:",
        "        raise HTTPException(status_code=409, detail=str(exc)) from exc",
        "    base = str(request.base_url).rstrip('/')",
        "    return ShortenResponse(code=code, short_url=f'{base}/{code}', original_url=str(payload.url))",
        "",
        "@app.get('/stats/{code}')",
        "def url_stats(code: str) -> dict:",
        "    stats = fetch_url_stats(code)",
        "    if not stats:",
        "        raise HTTPException(status_code=404, detail='Short URL not found')",
        "    return stats",
        "",
        "@app.get('/{code}')",
        "def redirect_url(code: str) -> RedirectResponse:",
        "    original_url = resolve_short_url(code)",
        "    if not original_url:",
        "        raise HTTPException(status_code=404, detail='Short URL not found')",
        "    return RedirectResponse(url=original_url, status_code=307)",
    ]

    test_lines = [
        "import pytest",
        "from app import service",
        "from fastapi.testclient import TestClient",
        "from app.main import app",
        "",
        "@pytest.fixture(autouse=True)",
        "def isolated_db(tmp_path, monkeypatch):",
        "    db_file = tmp_path / 'test_urls.db'",
        "    monkeypatch.setenv('SHORTENER_DB_PATH', str(db_file))",
        "",
        "client = TestClient(app)",
        "",
        "def test_health_check():",
        "    res = client.get('/health')",
        "    assert res.status_code == 200",
        "    assert res.json() == {'status': 'ok'}",
        "",
        "def test_shorten_redirect_and_analytics():",
        "    create_res = client.post('/shorten', json={'url': 'https://example.com'})",
        "    assert create_res.status_code == 201",
        "    code = create_res.json()['code']",
        "    redirect_res = client.get(f'/{code}', follow_redirects=False)",
        "    assert redirect_res.status_code == 307",
        "    assert redirect_res.headers['location'] == 'https://example.com/'",
        "    stats_res = client.get(f'/stats/{code}')",
        "    assert stats_res.status_code == 200",
        "    assert stats_res.json()['original_url'] == 'https://example.com/'",
        "    assert stats_res.json()['created_at']",
        "    assert stats_res.json()['clicks'] == 1",
        "",
        "def test_create_short_url_retries_code_collisions(monkeypatch):",
        "    generated_codes = iter(['duplicate', 'available'])",
        "    saved_codes = []",
        "    monkeypatch.setattr(service, 'generate_code', lambda: next(generated_codes))",
        "    monkeypatch.setattr(service, 'save_url', lambda code, url: saved_codes.append(code) or code == 'available')",
        "    assert service.create_short_url('https://example.com/') == 'available'",
        "    assert saved_codes == ['duplicate', 'available']",
        "",
        "def test_custom_alias_conflict():",
        "    res1 = client.post('/shorten', json={'url': 'https://example.com', 'custom_alias': 'my-link'})",
        "    assert res1.status_code == 201",
        "    res2 = client.post('/shorten', json={'url': 'https://example.com', 'custom_alias': 'my-link'})",
        "    assert res2.status_code == 409",
        "",
        "def test_invalid_url_rejected():",
        "    res = client.post('/shorten', json={'url': 'not-a-valid-url'})",
        "    assert res.status_code == 422",
    ]

    files = [
        {"path": "app/__init__.py", "content": ""},
        {"path": "app/storage.py", "content": "\n".join(storage_lines) + "\n"},
        {"path": "app/service.py", "content": "\n".join(service_lines) + "\n"},
        {"path": "app/main.py", "content": "\n".join(main_lines) + "\n"},
        {"path": "tests/test_shortener.py", "content": "\n".join(test_lines) + "\n"},
        {
            "path": "README.md",
            "content": (
                "# URL Shortener Service\n\n"
                "Runnable FastAPI + SQLite demo with short-link creation, redirects, and click stats.\n\n"
                "Requires Python 3.10 or newer.\n\n"
                "## Run locally\n\n"
                "```powershell\n"
                "python -m venv .venv\n"
                ".venv\\Scripts\\Activate.ps1\n"
                "python -m pip install -r requirements.txt\n"
                "python -m uvicorn app.main:app --reload\n"
                "```\n\n"
                "Open http://127.0.0.1:8000/docs. Run tests from this directory with `python -m pytest`.\n\n"
                "## API\n\n"
                "- `POST /shorten` with `{\"url\":\"https://example.com\"}` creates a short link.\n"
                "- `GET /{code}` returns a 307 redirect and increments the click count.\n"
                "- `GET /stats/{code}` returns the original URL, creation time, and clicks.\n"
                "- `GET /health` checks service availability.\n\n"
                "This SQLite backend is for local evaluation. Optional future scale-out notes in "
                "`docs/URL_SHORTENER_SCALABILITY.md` describe possible evolution, not a "
                "requirement for running this demo."
            ),
        },
        {
            "path": "requirements.txt",
            "content": (
                "fastapi>=0.110,<1.0\n"
                "httpx>=0.27,<1.0\n"
                "pydantic>=2.6,<3.0\n"
                "pytest>=8.0,<10.0\n"
                "uvicorn>=0.27,<1.0\n"
            ),
        },
        {
            "path": "docs/URL_SHORTENER_SCALABILITY.md",
            "content": (
                "# Optional URL Shortener Scale-out Considerations\n\n"
                "The generated app is a zero-setup SQLite reference implementation. The following "
                "notes are optional future evolution, not requirements for this runnable demo.\n\n"
                "## Target architecture\n\n"
                "- Run stateless FastAPI instances behind a load balancer; externalize configuration and secrets.\n"
                "- Store authoritative URL mappings and uniqueness constraints in PostgreSQL. Generate random "
                "Base62 codes and let a unique index arbitrate collisions; retry only on unique-key conflicts.\n"
                "- Use Redis as a cache-aside read-through layer for redirects, with bounded TTL and explicit "
                "invalidation on link changes. The database remains authoritative.\n"
                "- Publish click events asynchronously to a durable queue (for example Kafka or Azure Event Hubs). "
                "A consumer deduplicates by event ID and aggregates counts into a separate analytics store. "
                "Redirect latency must not wait on analytics aggregation.\n"
                "- Apply rate limits, request timeouts, health/readiness probes, structured logs, tracing, and "
                "metrics for cache hit rate, redirect latency, queue lag, and database saturation.\n\n"
                "## Consistency and failure behavior\n\n"
                "The redirect lookup is strongly backed by the mapping store on cache miss. Analytics are "
                "eventually consistent; queue outages must be visible through lag/alerts and handled with "
                "bounded retries or a durable outbox. Define event retention and privacy policy before launch. "
                "Avoid silently dropping events or making a failed analytics write turn a valid redirect into "
                "an error.\n\n"
                "## Capacity and validation gates\n\n"
                "Benchmark read/write mix, p95/p99 redirect latency, cache hit rate, database connection limits, "
                "and queue throughput using representative load. Exercise cache eviction, database failover, "
                "queue backpressure, duplicate events, and recovery. No production load or failover test is "
                "claimed by this local prototype.\n\n"
                "## Migration path\n\n"
                "Keep API contracts stable; introduce a storage interface, migrate SQLite rows to PostgreSQL, "
                "dual-read/verify before cutover, then add Redis and asynchronous click ingestion behind "
                "feature flags. The runnable demo currently performs synchronous SQLite click increments."
            ),
        },
    ]
    return CodeBundle(
        files=files,
        api_contract_summary="POST /shorten, GET /{code}, GET /stats/{code}, GET /health",
        architecture_notes="Layered FastAPI -> Service -> SQLite architecture with isolated test DB fixture.",
    )


def _build_brownfield_ttl_bundle() -> CodeBundle:
    storage = textwrap.dedent(
        """\
        import os
        import sqlite3
        from datetime import datetime, timezone

        def get_db_path() -> str:
            return os.getenv("SHORTENER_DB_PATH", "url_shortener.db")

        def init_db() -> None:
            with sqlite3.connect(get_db_path()) as conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS urls ("
                    "code TEXT PRIMARY KEY, original_url TEXT NOT NULL, "
                    "created_at TEXT NOT NULL, clicks INTEGER NOT NULL DEFAULT 0, "
                    "expires_at TEXT)"
                )
                columns = {
                    row[1] for row in conn.execute("PRAGMA table_info(urls)").fetchall()
                }
                if "expires_at" not in columns:
                    conn.execute("ALTER TABLE urls ADD COLUMN expires_at TEXT")
                conn.commit()

        def save_url(
            code: str, original_url: str, expires_at: str | None = None
        ) -> bool:
            init_db()
            try:
                with sqlite3.connect(get_db_path()) as conn:
                    conn.execute(
                        "INSERT INTO urls "
                        "(code, original_url, created_at, clicks, expires_at) "
                        "VALUES (?, ?, ?, 0, ?)",
                        (
                            code,
                            original_url,
                            datetime.now(timezone.utc).isoformat(),
                            expires_at,
                        ),
                    )
                    conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

        def get_url_state_and_increment(
            code: str, now: datetime | None = None
        ) -> tuple[str | None, bool]:
            init_db()
            current_time = now or datetime.now(timezone.utc)
            if current_time.tzinfo is None:
                current_time = current_time.replace(tzinfo=timezone.utc)
            current_time = current_time.astimezone(timezone.utc)

            with sqlite3.connect(get_db_path()) as conn:
                row = conn.execute(
                    "SELECT original_url, expires_at FROM urls WHERE code = ?", (code,)
                ).fetchone()
                if not row:
                    return None, False

                if row[1]:
                    expires_at = datetime.fromisoformat(row[1])
                    if expires_at.tzinfo is None:
                        expires_at = expires_at.replace(tzinfo=timezone.utc)
                    if expires_at.astimezone(timezone.utc) <= current_time:
                        return None, True

                conn.execute("UPDATE urls SET clicks = clicks + 1 WHERE code = ?", (code,))
                conn.commit()
                return row[0], False

        def get_url_and_increment(code: str) -> str | None:
            url, _ = get_url_state_and_increment(code)
            return url

        def get_stats(code: str) -> dict | None:
            init_db()
            with sqlite3.connect(get_db_path()) as conn:
                row = conn.execute(
                    "SELECT code, original_url, created_at, clicks, expires_at "
                    "FROM urls WHERE code = ?",
                    (code,),
                ).fetchone()
                if not row:
                    return None
                return {
                    "code": row[0],
                    "original_url": row[1],
                    "created_at": row[2],
                    "clicks": row[3],
                    "expires_at": row[4],
                }
        """
    )
    service = textwrap.dedent(
        """\
        import secrets
        import string
        from datetime import datetime, timedelta, timezone
        from app.storage import (
            get_stats,
            get_url_state_and_increment,
            save_url,
        )

        ALPHABET = string.ascii_letters + string.digits

        def generate_code(length: int = 6) -> str:
            return "".join(secrets.choice(ALPHABET) for _ in range(length))

        def create_short_url(
            original_url: str,
            custom_alias: str | None = None,
            ttl_seconds: int | None = None,
        ) -> str:
            if ttl_seconds is not None and ttl_seconds <= 0:
                raise ValueError("TTL must be a positive number of seconds.")
            expires_at = None
            if ttl_seconds is not None:
                expires_at = (
                    datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
                ).isoformat()

            if custom_alias:
                if not save_url(custom_alias, original_url, expires_at):
                    raise ValueError("Custom alias already exists.")
                return custom_alias
            for _ in range(5):
                code = generate_code()
                if save_url(code, original_url, expires_at):
                    return code
            raise RuntimeError("Failed to generate unique short code.")

        def resolve_short_url_state(code: str) -> tuple[str | None, bool]:
            return get_url_state_and_increment(code)

        def resolve_short_url(code: str) -> str | None:
            url, _ = resolve_short_url_state(code)
            return url

        def fetch_url_stats(code: str) -> dict | None:
            return get_stats(code)
        """
    )
    main = textwrap.dedent(
        """\
        from contextlib import asynccontextmanager
        from fastapi import FastAPI, HTTPException, Request
        from fastapi.responses import RedirectResponse
        from pydantic import BaseModel, Field, HttpUrl
        from app.service import (
            create_short_url,
            fetch_url_stats,
            resolve_short_url_state,
        )
        from app.storage import init_db

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            init_db()
            yield

        app = FastAPI(
            title="Agent-Generated URL Shortener",
            version="1.0.0",
            lifespan=lifespan,
        )

        class ShortenRequest(BaseModel):
            url: HttpUrl
            custom_alias: str | None = Field(
                default=None, min_length=3, max_length=20, pattern="^[a-zA-Z0-9_-]+$"
            )
            ttl_seconds: int | None = Field(default=None, gt=0)

        class ShortenResponse(BaseModel):
            code: str
            short_url: str
            original_url: str

        @app.get("/health")
        def health() -> dict:
            return {"status": "ok"}

        @app.post("/shorten", response_model=ShortenResponse, status_code=201)
        def shorten_url(payload: ShortenRequest, request: Request) -> ShortenResponse:
            try:
                code = create_short_url(
                    str(payload.url), payload.custom_alias, payload.ttl_seconds
                )
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            base = str(request.base_url).rstrip("/")
            return ShortenResponse(
                code=code,
                short_url=f"{base}/{code}",
                original_url=str(payload.url),
            )

        @app.get("/stats/{code}")
        def url_stats(code: str) -> dict:
            stats = fetch_url_stats(code)
            if not stats:
                raise HTTPException(status_code=404, detail="Short URL not found")
            return stats

        @app.get("/{code}")
        def redirect_url(code: str) -> RedirectResponse:
            original_url, expired = resolve_short_url_state(code)
            if expired:
                raise HTTPException(status_code=410, detail="Short URL has expired")
            if not original_url:
                raise HTTPException(status_code=404, detail="Short URL not found")
            return RedirectResponse(url=original_url, status_code=307)
        """
    )
    tests = textwrap.dedent(
        """\
        import sqlite3

        import pytest
        from app import service
        from app.main import app
        from app.storage import get_stats, init_db, save_url
        from fastapi.testclient import TestClient

        @pytest.fixture(autouse=True)
        def isolated_db(tmp_path, monkeypatch):
            db_file = tmp_path / "test_urls.db"
            monkeypatch.setenv("SHORTENER_DB_PATH", str(db_file))

        client = TestClient(app)

        def test_health_check():
            response = client.get("/health")
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}

        def test_shorten_redirect_and_analytics():
            create_response = client.post(
                "/shorten", json={"url": "https://example.com"}
            )
            assert create_response.status_code == 201
            code = create_response.json()["code"]
            redirect_response = client.get(f"/{code}", follow_redirects=False)
            assert redirect_response.status_code == 307
            assert redirect_response.headers["location"] == "https://example.com/"
            stats_response = client.get(f"/stats/{code}")
            assert stats_response.status_code == 200
            assert stats_response.json()["original_url"] == "https://example.com/"
            assert stats_response.json()["created_at"]
            assert stats_response.json()["clicks"] == 1

        def test_create_short_url_retries_code_collisions(monkeypatch):
            generated_codes = iter(["duplicate", "available"])
            saved_codes = []
            monkeypatch.setattr(
                service, "generate_code", lambda: next(generated_codes)
            )
            monkeypatch.setattr(
                service,
                "save_url",
                lambda code, url, expires_at=None: saved_codes.append(code)
                or code == "available",
            )
            assert service.create_short_url("https://example.com/") == "available"
            assert saved_codes == ["duplicate", "available"]

        def test_custom_alias_conflict():
            first = client.post(
                "/shorten",
                json={"url": "https://example.com", "custom_alias": "my-link"},
            )
            assert first.status_code == 201
            second = client.post(
                "/shorten",
                json={"url": "https://example.com", "custom_alias": "my-link"},
            )
            assert second.status_code == 409

        def test_invalid_url_rejected():
            response = client.post("/shorten", json={"url": "not-a-valid-url"})
            assert response.status_code == 422

        def test_ttl_is_optional_and_persisted():
            response = client.post(
                "/shorten",
                json={"url": "https://example.com", "ttl_seconds": 3600},
            )
            assert response.status_code == 201
            stats = client.get(f"/stats/{response.json()['code']}").json()
            assert stats["expires_at"]

        def test_non_positive_ttl_is_rejected():
            response = client.post(
                "/shorten",
                json={"url": "https://example.com", "ttl_seconds": 0},
            )
            assert response.status_code == 422

        def test_expired_link_returns_410_without_incrementing_clicks():
            assert save_url(
                "expired", "https://example.com/", "2000-01-01T00:00:00+00:00"
            )
            response = client.get("/expired", follow_redirects=False)
            assert response.status_code == 410
            assert get_stats("expired")["clicks"] == 0

        def test_unknown_link_remains_404():
            response = client.get("/unknown", follow_redirects=False)
            assert response.status_code == 404

        def test_legacy_database_schema_is_migrated(tmp_path, monkeypatch):
            db_file = tmp_path / "legacy.db"
            monkeypatch.setenv("SHORTENER_DB_PATH", str(db_file))
            with sqlite3.connect(db_file) as conn:
                conn.execute(
                    "CREATE TABLE urls (code TEXT PRIMARY KEY, "
                    "original_url TEXT NOT NULL, created_at TEXT NOT NULL, "
                    "clicks INTEGER NOT NULL DEFAULT 0)"
                )
                conn.execute(
                    "INSERT INTO urls VALUES (?, ?, ?, ?)",
                    ("legacy", "https://example.com/", "2025-01-01T00:00:00+00:00", 3),
                )
            init_db()
            stats = get_stats("legacy")
            assert stats["clicks"] == 3
            assert stats["expires_at"] is None

        """
    )
    readme = textwrap.dedent(
        """\
        # URL Shortener Service

        Runnable FastAPI + SQLite demo with short-link creation, redirects, click stats,
        and optional link expiration.

        ## Run locally

        ```powershell
        python -m pip install -r requirements.txt
        python -m uvicorn app.main:app --reload
        ```

        Open http://127.0.0.1:8000/docs. Run tests with `python -m pytest`.

        ## API

        - `POST /shorten` accepts `url`, optional `custom_alias`, and optional positive
          `ttl_seconds`.
        - `GET /{code}` returns a 307 redirect, increments clicks for active links,
          returns 410 for expired links, and 404 for unknown links.
        - `GET /stats/{code}` returns the original URL, creation time, click count,
          and optional `expires_at`.
        - `GET /health` checks service availability.

        Existing SQLite databases are migrated additively; links without an expiration
        remain active indefinitely.
        """
    )
    return CodeBundle(
        files=[
            {"path": "app/storage.py", "content": storage},
            {"path": "app/service.py", "content": service},
            {"path": "app/main.py", "content": main},
            {"path": "tests/test_shortener.py", "content": tests},
            {"path": "README.md", "content": readme},
        ],
        api_contract_summary=(
            "POST /shorten supports optional ttl_seconds; GET /{code} returns 410 when expired."
        ),
        architecture_notes=(
            "Brownfield SQLite enhancement with additive expires_at migration and UTC expiration."
        ),
    )


def _build_ambiguous_sharing_bundle() -> CodeBundle:
    content = textwrap.dedent(
        """\
        # Ambiguous Requirement: Make Links Easier to Share

        ## Original request

        > Make links easier to share.

        ## Interpretation used for this run

        Assume the user wants memorable short links. Do not assume they requested a
        frontend, clipboard button, QR code, or social-media integration. Keep the
        existing HTTP(S)-only validation, leave links non-expiring by default, and
        retain aggregate click counts without visitor identification.

        ## Existing-code evidence

        The existing `POST /shorten` endpoint accepts an optional `custom_alias`.
        Aliases are validated, duplicate aliases return HTTP 409, and the URL shortener
        tests exercise that conflict behavior. Under the stated assumption, the current
        feature already addresses the request, so this run makes no application-code
        changes and avoids duplicating behavior.

        ## Clarification needed for broader work

        If the user means a one-click copy action, QR code, share sheet, or social
        integration, ask which client and sharing workflow they want before estimating
        or implementing it. The current service has no frontend or QR generation.

        ## Validation

        Ruff and the existing pytest suite were run against the brownfield workspace.
        This report records a scoped interpretation; it does not claim that a sharing UI
        or QR feature was built.
        """
    )
    return CodeBundle(
        files=[
            {"path": "docs/AMBIGUOUS_REQUIREMENT.md", "content": content},
        ],
        api_contract_summary="No API changes; existing POST /shorten custom_alias behavior is reused.",
        architecture_notes=(
            "Ambiguous request resolved with explicit assumptions and existing-code evidence; "
            "no application changes."
        ),
    )
