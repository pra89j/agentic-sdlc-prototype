# Agentic Software Engineering System (SDLC Prototype)

An end-to-end agentic software engineering workflow prototype that transforms a requirement into an approved task plan, generated engineering artifacts, validation results, and a review summary. Its demoable mandatory example is a **FastAPI + SQLite URL Shortener**. The scale-out notes are optional future considerations; the app is intentionally a small local demo, not a production deployment.

## Architecture Overview

```text
[Requirement Input]
       │
       ▼
1. Requirement Analyst  ──► Normalizes intent & logs explicit assumptions
       │
       ▼
2. Codebase Reasoner    ──► Inspects AST symbols & file dependencies (Brownfield)
       │
       ▼
3. Task Architect       ──► Generates dependency DAG
       │
       ▼
4. Human Approval       ──► Approve / reject before generated writes
       │                    │
       ▼                    │
5. DAG Task Executors   ◄──┘ Run dependency-ready waves; independent tasks run concurrently
       ▼
6. Validation Gate      ──► `ruff` + `pytest`, with bounded repair loop (max 3 attempts)
       │ (Passed or retry limit)
       ▼
7. Critic & Summary     ──► Risk report + `ENGINEERING_SUMMARY.md` + execution trace
```

## Quickstart Setup

Use Python 3.10 or newer.

### 1. Create Virtual Environment & Install Dependencies
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure API Key (Optional for Offline Demo)
For a live Gemini run, create an API key in [Google AI Studio](https://aistudio.google.com/api-keys),
then set it in the current PowerShell session. Replace the placeholder locally; never commit
the real key or paste it into a workspace file.

```powershell
$env:LLM_PROVIDER = "gemini"
$env:GEMINI_MODEL = "gemini-4-hydrogen"
$env:GEMINI_API_KEY = "<your-google-ai-studio-api-key>"
```

The key is only needed by the workflow runner, not by the generated URL shortener. Mock
examples run offline and do not need a key. Remove the key from the current session when
finished with `Remove-Item Env:GEMINI_API_KEY`.

### 3. Run the Agentic SDLC Workflow
**Greenfield Build (or Offline Mock Demo):**
```bash
python run_agent.py --prompt "Build a runnable URL shortener service with click analytics" --mock
```
Review the printed plan and type `y` to approve. Add `--approve-plan` only when approval has
already been granted (for example, in a controlled CI run):
```bash
python run_agent.py --prompt "Build a scalable URL shortener service with APIs, persistence, and analytics" --mock --approve-plan
```

**Live LLM Greenfield + Brownfield Enhancement** (requires a provider API key; interactive approval is still required):
```powershell
# PowerShell: obtain a Gemini API key from Google AI Studio, then:
$env:LLM_PROVIDER = "gemini"
$env:GEMINI_API_KEY = "<your-key>"
$env:GEMINI_MODEL = "gemini-4-hydrogen"

# Step 1: Greenfield generation
python run_agent.py --prompt "Build a URL shortener web service"

# Step 2: Brownfield feature addition on the generated codebase
python run_agent.py --prompt "Add optional link expiration TTL in seconds and return 410 Gone when expired"
```

**Offline Brownfield + Ambiguous Scenarios** (deterministic demos; no API key required):
```powershell
Copy-Item -Recurse workspace\url_shortener workspace\examples\brownfield-ttl-rerun
python run_agent.py --prompt "Add optional link expiration TTL in seconds and return 410 Gone when expired" --workspace workspace\examples\brownfield-ttl-rerun --mock

Copy-Item -Recurse workspace\url_shortener workspace\examples\ambiguous-sharing-rerun
python run_agent.py --prompt "Make links easier to share." --workspace workspace\examples\ambiguous-sharing-rerun --mock
```
Review the assumptions and plan before approving either run. The brownfield scenario
implements TTL; the ambiguous scenario documents a narrow alias-based interpretation
because the existing API already supports aliases, and it does not claim to implement a UI.
These are deterministic mock demonstrations, not live LLM runs. See
[`docs/EXAMPLE_SCENARIOS.md`](docs/EXAMPLE_SCENARIOS.md) for separate live commands,
verification criteria, and the recorded status of both modes.
Gemini free-tier quotas and model access can change. Google’s free-tier terms may allow submitted
content to be used to improve its products; do not send confidential source code or secrets.

**Recorded live ambiguous-sharing example** (uses the environment settings above):
```powershell
Copy-Item -Recurse workspace\url_shortener workspace\examples\ambiguous-sharing-live-rerun
python run_agent.py --prompt "Make links easier to share." --workspace workspace\examples\ambiguous-sharing-live-rerun
```
Review the proposed plan and enter `y` to approve. The successful user-run output is kept
in `workspace\examples\ambiguous-sharing-live`; its trace records live mode and passed
validation. See the [scenario notes](docs/EXAMPLE_SCENARIOS.md) for the mock and live
walkthroughs.

### 4. Run the Generated URL Shortener Application
```bash
cd workspace/url_shortener
python -m uvicorn app.main:app --reload
```
Open **http://127.0.0.1:8000/docs** to test the interactive OpenAPI endpoints (`POST /shorten`, `GET /{code}`, `GET /stats/{code}`).

The generated project includes its own `requirements.txt`. From inside `workspace/url_shortener`, a standalone setup is:
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```
Run `python -m pytest` in that directory to exercise the API and service behavior.

## Reviewable Outputs
- `execution_trace.json` — normalized requirement, impact analysis, DAG, approval, task waves, and validation results.
- `ENGINEERING_SUMMARY.md` — implementation plan, artifacts, risks, trade-offs, assumptions, and limitations.
- `RISK_AND_VALIDATION.md` — exact lint/test output and risk review.
- `docs/EXAMPLE_SCENARIOS.md` — greenfield, brownfield, and ambiguous requirement walkthroughs.
- `docs/URL_SHORTENER_SCALABILITY.md` — optional future scale-out considerations; the generated SQLite app remains the runnable demo.

## Repository Structure
- `agent_engine/` — LangGraph workflow, Pydantic schemas, AST/sandbox tools, and specialized SDLC agents.
- `workspace/url_shortener/` — Runnable URL shortener application, automated tests, and validation report generated by the system.
- `docs/APPROACH_AND_DESIGN.md` — Architectural rationale, key decisions, assumptions, and production tradeoffs.
- `docs/EXAMPLE_SCENARIOS.md` — Sample requirements and representative review outputs.
- `docs/URL_SHORTENER_SCALABILITY.md` — Scale-out architecture and operational validation plan.
