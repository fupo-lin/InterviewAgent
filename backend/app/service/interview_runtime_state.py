from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict


class InterviewRuntimeState(TypedDict, total=False):
    workflow_id: str
    workflow_run_id: str
    thread_id: str
    status: str
    active_step: str | None
    project_id: int | None
    session_id: int
    session_uid: str
    role_name: str
    interview_plan_id: int | None
    execution_id: int | None
    current_section_key: str | None
    current_section_index: int
    current_section_round_no: int
    total_completed_round_no: int
    next_action: str | None
    route_after_advance: str | None
    route_after_advance_reason: str | None
    runtime_decision: dict | None
    open_threads: list[dict]
    memory_refs: dict
    incoming_user_input: str | None
    expected_user_round_no: int | None
    last_user_message_id: int | None
    last_assistant_message_id: int | None
    last_topic_judge_agent_run_id: int | None
    last_followup_agent_run_id: int | None
    last_memory_agent_run_ids: list[int]
    latest_candidate_memory_id: int | None
    latest_conversation_summary_id: int | None
    completed_steps: list[str]
    failed_steps: list[str]
    last_error: dict | None
    resume_reason: str | None
    resume_from_step: str | None


@dataclass(frozen=True)
class RuntimeContext:
    latest_completed_round_no: int
    recent_history: list[Any]
    execution: Any | None
    candidate_profile: Any | None
    conversation_summary: Any | None
    plan_context: str | None
    execution_context: str | None
    open_threads: list[dict] | None = None
    retrieved_evidence_context: str | None = None
