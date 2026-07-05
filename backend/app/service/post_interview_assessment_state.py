from __future__ import annotations

from typing import TypedDict


class AssessmentConditionCheck(TypedDict, total=False):
    name: str
    ok: bool
    value: str | int | bool | None
    detail: str


class AssessmentBranchDecision(TypedDict, total=False):
    step_id: str
    branch: str
    reason: str
    condition_checks: list[AssessmentConditionCheck]


class AssessmentOutputArtifact(TypedDict, total=False):
    name: str
    artifact_kind: str
    artifact_id: int | None
    source: str
    required: bool
    status: str
    reason: str | None


class AssessmentNextAction(TypedDict, total=False):
    type: str
    reason: str
    artifact_name: str | None


class AssessmentOutputs(TypedDict, total=False):
    contract_version: str
    artifacts: list[AssessmentOutputArtifact]
    next_actions: list[AssessmentNextAction]


class PostInterviewAssessmentState(TypedDict, total=False):
    workflow_id: str
    workflow_run_id: str
    thread_id: str
    status: str
    active_step: str | None
    project_id: int | None
    session_id: int
    session_uid: str
    incoming_trigger: str
    evaluation_id: int | None
    evaluation_agent_run_id: int | None
    execution_id: int | None
    candidate_profile_summary_id: int | None
    conversation_summary_id: int | None
    completed_steps: list[str]
    skipped_steps: list[str]
    failed_steps: list[str]
    last_error: dict | None
    partial_reason: str | None
    resume_reason: str | None
    resume_from_step: str | None
    branch: str | None
    branch_reason: str | None
    branch_decisions: list[AssessmentBranchDecision]
    output_contract_version: str
    outputs: AssessmentOutputs
    next_actions: list[AssessmentNextAction]
