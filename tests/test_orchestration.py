import builtins

import pytest

from agent_engine.nodes import (
    _build_ambiguous_sharing_bundle,
    _build_brownfield_ttl_bundle,
    _generate_validated_task_dag,
    _mock_scenario,
)
from agent_engine.schemas import TaskDAG
from agent_engine.tools import task_execution_waves, write_files
from agent_engine.workflow import build_sdlc_graph


def test_task_execution_waves_group_independent_tasks():
    tasks = [
        {"id": "storage", "dependencies": [], "target_files": ["app/storage.py"]},
        {"id": "api", "dependencies": ["storage"], "target_files": ["app/main.py"]},
        {"id": "docs", "dependencies": ["storage"], "target_files": ["README.md"]},
        {"id": "tests", "dependencies": ["api", "docs"], "target_files": ["tests/test_app.py"]},
    ]

    waves = task_execution_waves(tasks, ["storage", "api", "docs", "tests"])

    assert [[task["id"] for task in wave] for wave in waves] == [
        ["storage"],
        ["api", "docs"],
        ["tests"],
    ]


@pytest.mark.parametrize(
    ("tasks", "message"),
    [
        (
            [{"id": "a", "dependencies": ["missing"], "target_files": ["a.py"]}],
            "unknown task",
        ),
        (
            [
                {"id": "a", "dependencies": ["b"], "target_files": ["a.py"]},
                {"id": "b", "dependencies": ["a"], "target_files": ["b.py"]},
            ],
            "cycle",
        ),
        (
            [
                {"id": "a", "dependencies": [], "target_files": ["same.py"]},
                {"id": "b", "dependencies": [], "target_files": ["same.py"]},
            ],
            "assigned to both",
        ),
        (
            [{"id": "a", "dependencies": [], "target_files": ["../outside.py"]}],
            "Unsafe task target path",
        ),
    ],
)
def test_invalid_task_dags_fail_closed(tasks, message):
    with pytest.raises(ValueError, match=message):
        task_execution_waves(tasks)


def test_execution_order_must_respect_dependencies():
    tasks = [
        {"id": "a", "dependencies": [], "target_files": ["a.py"]},
        {"id": "b", "dependencies": ["a"], "target_files": ["b.py"]},
    ]

    with pytest.raises(ValueError, match="places b before dependency a"):
        task_execution_waves(tasks, ["b", "a"])


def test_file_writer_rejects_path_escape(tmp_path):
    with pytest.raises(ValueError, match="Unsafe path traversal"):
        write_files(tmp_path / "workspace", [{"path": "../outside.txt", "content": "no"}])


def test_mock_scenario_templates_cover_brownfield_and_ambiguous_cases():
    assert _mock_scenario(
        "Add optional link expiration TTL in seconds and return 410 Gone when expired"
    ) == "brownfield_ttl"
    assert _mock_scenario("Make links easier to share.") == "ambiguous_sharing"

    ttl_files = {
        file.path: file.content for file in _build_brownfield_ttl_bundle().files
    }
    assert set(ttl_files) == {
        "app/storage.py",
        "app/service.py",
        "app/main.py",
        "tests/test_shortener.py",
        "README.md",
    }
    assert "ALTER TABLE urls ADD COLUMN expires_at TEXT" in ttl_files["app/storage.py"]
    assert 'status_code=410' in ttl_files["app/main.py"]
    assert "test_legacy_database_schema_is_migrated" in ttl_files["tests/test_shortener.py"]

    ambiguous_files = {
        file.path: file.content for file in _build_ambiguous_sharing_bundle().files
    }
    assert set(ambiguous_files) == {"docs/AMBIGUOUS_REQUIREMENT.md"}
    assert "no application-code" in ambiguous_files["docs/AMBIGUOUS_REQUIREMENT.md"]


def test_invalid_live_plan_is_repaired_before_approval():
    invalid_dag = TaskDAG(
        tasks=[
            {
                "id": "T1",
                "title": "API contract",
                "category": "contract",
                "dependencies": [],
                "target_files": ["app/main.py"],
                "acceptance_criteria": "Define the contract.",
            },
            {
                "id": "T2",
                "title": "API routes",
                "category": "implementation",
                "dependencies": ["T1"],
                "target_files": ["app/main.py"],
                "acceptance_criteria": "Implement the routes.",
            },
        ],
        execution_order=["T1", "T2"],
    )
    valid_dag = TaskDAG(
        tasks=[
            {
                "id": "T1",
                "title": "API contract",
                "category": "contract",
                "dependencies": [],
                "target_files": ["app/contracts.py"],
                "acceptance_criteria": "Define the contract.",
            },
            {
                "id": "T2",
                "title": "API routes",
                "category": "implementation",
                "dependencies": ["T1"],
                "target_files": ["app/main.py"],
                "acceptance_criteria": "Implement the routes.",
            },
        ],
        execution_order=["T1", "T2"],
    )

    class FakePlanner:
        def __init__(self):
            self.prompts = []
            self.responses = [invalid_dag, valid_dag]

        def invoke(self, prompt):
            self.prompts.append(prompt)
            return self.responses.pop(0)

    planner = FakePlanner()
    result = _generate_validated_task_dag(planner, "Create a plan.")

    assert result == valid_dag.model_dump()
    assert len(planner.prompts) == 2
    assert "assigned to both" in planner.prompts[1]
    assert "exactly one task" in planner.prompts[1]


def test_rejected_plan_stops_before_generating_files(tmp_path, monkeypatch):
    monkeypatch.setattr(builtins, "input", lambda _: "no")
    state = {
        "requirement": "Build a URL shortener",
        "workspace_path": str(tmp_path / "target"),
        "mock_mode": True,
        "retry_count": 0,
        "validation_passed": False,
        "validation_logs": "",
        "auto_approve": False,
        "approved": False,
        "approval_source": "pending",
        "execution_log": [],
        "workflow_status": "awaiting_approval",
    }

    result = build_sdlc_graph().invoke(state)

    assert result["approved"] is False
    assert result["approval_source"] == "rejected"
    assert not (tmp_path / "target" / "app" / "main.py").exists()
