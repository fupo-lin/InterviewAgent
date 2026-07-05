from __future__ import annotations

from uuid import uuid4

from app.service.workflow_state_contract import WorkflowStateValidator


class WorkflowRuntime:
    def __init__(self, repository, state_validator: WorkflowStateValidator | None = None):
        self.repository = repository
        self.state_validator = state_validator or WorkflowStateValidator()

    def load_or_create(
        self,
        *,
        workflow_id: str,
        thread_id: str,
        project_id: int | None,
        session_id: int | None,
        initial_state: dict,
    ):
        existing = self.repository.get_by_thread_id(thread_id)
        if existing:
            return existing
        workflow_run_id = f"{workflow_id}_{uuid4().hex}"
        validated_state = self.state_validator.validate(initial_state or {})
        return self.repository.create(
            workflow_run_id=workflow_run_id,
            workflow_id=workflow_id,
            thread_id=thread_id,
            project_id=project_id,
            session_id=session_id,
            status="running",
            current_step="start",
            state=validated_state,
        )

    def save(
        self,
        workflow_run,
        *,
        state: dict,
        current_step: str,
        status: str = "running",
        last_error: dict | None = None,
    ):
        validated_state = self.state_validator.validate(state)
        return self.repository.save_state(
            workflow_run,
            state=validated_state,
            current_step=current_step,
            status=status,
            last_error=last_error,
            error_message=(last_error or {}).get("message") if last_error else None,
        )
