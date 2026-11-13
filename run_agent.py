import argparse
import json
from pathlib import Path
from dotenv import load_dotenv
from agent_engine.workflow import build_sdlc_graph


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Agentic Software Engineering System")
    parser.add_argument("--prompt", required=True, help="Software requirement or enhancement request")
    parser.add_argument("--workspace", default="workspace/url_shortener", help="Target repository path")
    parser.add_argument("--mock", action="store_true", help="Run supported deterministic offline URL-shortener demos")
    parser.add_argument(
        "--approve-plan",
        action="store_true",
        help="Approve the printed task plan without an interactive prompt",
    )
    args = parser.parse_args()

    app = build_sdlc_graph()
    initial_state = {
        "requirement": args.prompt,
        "workspace_path": args.workspace,
        "mock_mode": args.mock,
        "retry_count": 0,
        "validation_passed": False,
        "validation_logs": "",
        "auto_approve": args.approve_plan,
        "approved": False,
        "approval_source": "pending",
        "execution_log": [],
        "workflow_status": "awaiting_approval",
    }

    final_state = app.invoke(initial_state)

    trace_path = Path(args.workspace) / "execution_trace.json"
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text(json.dumps(final_state, indent=2), encoding="utf-8")

    print("\n=== SDLC Workflow Complete ===")
    print(f"Workspace:  {args.workspace}")
    print(f"Approved:   {final_state['approved']}")
    print(f"Validated:  {final_state['validation_passed']}")
    print(f"Status:     {final_state['workflow_status']}")
    if final_state["approved"]:
        print(
            "Artifacts:  app/, tests/, docs/, README.md, RISK_AND_VALIDATION.md, "
            "ENGINEERING_SUMMARY.md, execution_trace.json"
        )
    else:
        print("Artifacts:  execution_trace.json (plan and rejection/approval status only)")


if __name__ == "__main__":
    main()
