from __future__ import annotations

from typing import TypedDict


class GrowthReportConditionCheck(TypedDict, total=False):
    name: str
    ok: bool
    value: str | int | bool | None
    detail: str


class GrowthReportBranchDecision(TypedDict, total=False):
    step_id: str
    branch: str
    reason: str
    condition_checks: list[GrowthReportConditionCheck]


class GrowthReportOutputArtifact(TypedDict, total=False):
    name: str
    artifact_kind: str
    artifact_id: int | None
    source: str
    required: bool
    status: str
    reason: str | None


class CandidateGrowthReportState(TypedDict, total=False):
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
    execution_id: int | None
    jd_analysis_id: int | None
    resume_profile_id: int | None
    gap_analysis_id: int | None
    project_candidate_profile_id: int | None
    resume_authenticity_report_id: int | None
    growth_report_id: int | None
    growth_report_uid: str | None
    growth_agent_run_id: int | None
    evidence_packet_id: str | None
    completed_steps: list[str]
    skipped_steps: list[str]
    failed_steps: list[str]
    last_error: dict | None
    partial_reason: str | None
    missing_inputs: list[str]
    resume_reason: str | None
    resume_from_step: str | None
    branch: str | None
    branch_reason: str | None
    branch_decisions: list[GrowthReportBranchDecision]
    outputs: dict
    next_actions: list[dict]
