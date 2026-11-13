from typing import Literal
from pydantic import BaseModel, Field


class EngineeringSpec(BaseModel):
    mode: Literal["greenfield", "brownfield"] = Field(
        description="Whether this is a new build or modifying an existing codebase."
    )
    problem_statement: str = Field(description="Normalized, unambiguous engineering goal.")
    functional_requirements: list[str] = Field(description="Concrete system behaviors required.")
    non_functional_requirements: list[str] = Field(description="Performance, reliability, and security needs.")
    ambiguities_resolved: list[str] = Field(
        description="Explicit assumptions made to resolve missing or vague requirements."
    )


class CodebaseImpact(BaseModel):
    existing_files: list[str] = Field(default_factory=list)
    impacted_modules: list[str] = Field(default_factory=list)
    data_flow_summary: str = Field(default="Greenfield build — no prior codebase.")
    integration_risks: list[str] = Field(default_factory=list)


class TaskNode(BaseModel):
    id: str = Field(description="Unique task ID, e.g., T1, T2.")
    title: str
    category: Literal["contract", "implementation", "test", "documentation"]
    dependencies: list[str] = Field(default_factory=list, description="IDs of prerequisite tasks.")
    target_files: list[str] = Field(description="Relative file paths inside workspace.")
    acceptance_criteria: str


class TaskDAG(BaseModel):
    tasks: list[TaskNode]
    execution_order: list[str] = Field(description="Topologically sorted task IDs.")


class GeneratedFile(BaseModel):
    path: str = Field(description="Relative path inside the target workspace, e.g., app/main.py")
    content: str = Field(description="Complete, runnable file content.")


class CodeBundle(BaseModel):
    files: list[GeneratedFile]
    api_contract_summary: str
    architecture_notes: str


class RiskReport(BaseModel):
    technical_risks: list[str]
    tradeoffs_made: list[str]
    failure_scenarios: list[str]
    validation_strategy: str
    verification_status: str
