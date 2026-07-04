from __future__ import annotations

from app.service.interview_runtime_state import InterviewRuntimeState


def resume_interview_runtime_state(
    *,
    workflow_run,
    initial_state: InterviewRuntimeState,
    session,
    incoming_user_input: str,
) -> InterviewRuntimeState:
    """Build runtime state for a new turn, unfinished turn, or failed retry."""
    stored_state = dict(getattr(workflow_run, "state", None) or {})
    workflow_status = getattr(workflow_run, "status", None)
    current_step = getattr(workflow_run, "current_step", None)
    is_retry = workflow_status in {"running", "failed"}
    resolved_user_input = (
        stored_state.get("incoming_user_input")
        if is_retry and stored_state.get("incoming_user_input") is not None
        else incoming_user_input
    )
    state: InterviewRuntimeState = {
        **dict(initial_state),
        **stored_state,
    }

    state.update(
        {
            "workflow_id": initial_state["workflow_id"],
            "thread_id": initial_state["thread_id"],
            "project_id": session.project_id,
            "session_id": session.id,
            "session_uid": session.session_uid,
            "role_name": session.role_name,
            "interview_plan_id": session.interview_plan_id,
            "incoming_user_input": resolved_user_input,
            "status": "running",
            "active_step": None,
            "completed_steps": [],
            "failed_steps": [],
            "last_memory_agent_run_ids": [],
            "last_error": None,
            "resume_reason": _resume_reason(workflow_status),
            "resume_from_step": current_step,
        }
    )

    if workflow_run:
        state["workflow_run_id"] = workflow_run.workflow_run_id
    else:
        state.pop("workflow_run_id", None)

    return state


def _resume_reason(workflow_status: str | None) -> str:
    if workflow_status == "failed":
        return "failed_retry"
    if workflow_status == "running":
        return "unfinished_turn"
    return "new_user_input"
