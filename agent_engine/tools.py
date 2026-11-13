import ast
import subprocess
import sys
from pathlib import Path


def scan_workspace(workspace_dir: Path) -> dict:
    """Inspect existing files and extract Python AST functions/classes for brownfield reasoning."""
    if not workspace_dir.exists():
        return {"is_empty": True, "files": [], "symbols": {}}

    ignored_directories = {"__pycache__", ".pytest_cache", ".ruff_cache"}
    generated_files = {"execution_trace.json", "RISK_AND_VALIDATION.md", "ENGINEERING_SUMMARY.md"}
    files = []
    symbols = {}
    for path in sorted(workspace_dir.rglob("*")):
        if any(part in ignored_directories for part in path.parts):
            continue
        if path.is_file() and path.name not in generated_files:
            rel = str(path.relative_to(workspace_dir)).replace("\\", "/")
            files.append(rel)
            if path.suffix == ".py":
                try:
                    tree = ast.parse(path.read_text(encoding="utf-8"))
                    defs = [
                        f"{type(node).__name__}:{node.name}"
                        for node in ast.walk(tree)
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                    ]
                    symbols[rel] = defs
                except SyntaxError:
                    symbols[rel] = ["SyntaxError"]

    return {"is_empty": len(files) == 0, "files": files, "symbols": symbols}


def task_execution_waves(
    tasks: list[dict], execution_order: list[str] | None = None
) -> list[list[dict]]:
    """Validate a task DAG and return independent tasks grouped by dependency level."""
    if not tasks:
        raise ValueError("Task DAG must contain at least one task")

    task_by_id = {}
    claimed_paths = {}
    for task in tasks:
        task_id = task["id"]
        if task_id in task_by_id:
            raise ValueError(f"Duplicate task ID: {task_id}")
        task_by_id[task_id] = task

        if not task["target_files"]:
            raise ValueError(f"Task {task_id} must declare at least one target file")
        for target in task["target_files"]:
            target_path = Path(target)
            if target_path.is_absolute() or ".." in target_path.parts:
                raise ValueError(f"Unsafe task target path: {target}")
            normalized = target_path.as_posix()
            previous_task = claimed_paths.get(normalized)
            if previous_task is not None:
                raise ValueError(
                    f"Target file {normalized} is assigned to both "
                    f"{previous_task} and {task_id}"
                )
            claimed_paths[normalized] = task_id

    for task in tasks:
        for dependency in task["dependencies"]:
            if dependency not in task_by_id:
                raise ValueError(
                    f"Task {task['id']} depends on unknown task {dependency}"
                )
            if dependency == task["id"]:
                raise ValueError(f"Task {task['id']} cannot depend on itself")

    if execution_order is not None:
        if len(execution_order) != len(task_by_id) or set(execution_order) != set(task_by_id):
            raise ValueError("Execution order must contain every task exactly once")
        positions = {task_id: index for index, task_id in enumerate(execution_order)}
        for task in tasks:
            for dependency in task["dependencies"]:
                if positions[dependency] >= positions[task["id"]]:
                    raise ValueError(
                        f"Execution order places {task['id']} before dependency {dependency}"
                    )

    remaining = dict(task_by_id)
    completed = set()
    waves = []
    while remaining:
        ready = [
            task for task in remaining.values()
            if set(task["dependencies"]).issubset(completed)
        ]
        if not ready:
            raise ValueError("Task dependencies contain a cycle")
        waves.append(ready)
        for task in ready:
            completed.add(task["id"])
            del remaining[task["id"]]
    return waves


def read_workspace_files(workspace_dir: Path, max_chars: int = 12000) -> str:
    """Read existing source files for brownfield context."""
    chunks = []
    total = 0
    for path in sorted(workspace_dir.rglob("*.py")):
        if "__pycache__" in str(path):
            continue
        rel = str(path.relative_to(workspace_dir)).replace("\\", "/")
        content = path.read_text(encoding="utf-8")
        block = f"--- FILE: {rel} ---\n{content}\n"
        if total + len(block) > max_chars:
            break
        chunks.append(block)
        total += len(block)
    return "\n".join(chunks)


def write_files(workspace_dir: Path, files: list[dict]) -> list[str]:
    """Write generated files safely inside the target workspace."""
    workspace_dir.mkdir(parents=True, exist_ok=True)
    root = workspace_dir.resolve()
    written = []
    for f in files:
        relative_path = Path(f["path"])
        if relative_path.is_absolute():
            raise ValueError(f"Unsafe path traversal blocked: {f['path']}")
        target = (root / relative_path).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Unsafe path traversal blocked: {f['path']}") from exc
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f["content"], encoding="utf-8")
        written.append(f["path"])
    return written


def run_validation_suite(workspace_dir: Path) -> tuple[bool, str]:
    """Execute linter (ruff) and test suite (pytest) inside the workspace."""
    import os
    logs = []
    env = os.environ.copy()
    env["PYTHONPATH"] = str(workspace_dir.resolve())

    ruff_cmd = [sys.executable, "-m", "ruff", "check", ".", "--select", "E,F", "--ignore", "E501"]
    ruff_res = subprocess.run(ruff_cmd, cwd=workspace_dir, env=env, capture_output=True, text=True, timeout=20)
    logs.append(f"[RUFF EXIT {ruff_res.returncode}]\n{ruff_res.stdout}{ruff_res.stderr}".strip())

    pytest_cmd = [sys.executable, "-m", "pytest", "-v"]
    pytest_res = subprocess.run(pytest_cmd, cwd=workspace_dir, env=env, capture_output=True, text=True, timeout=30)
    logs.append(f"[PYTEST EXIT {pytest_res.returncode}]\n{pytest_res.stdout}{pytest_res.stderr}".strip())

    passed = (ruff_res.returncode == 0) and (pytest_res.returncode == 0)
    return passed, "\n\n".join(logs)
