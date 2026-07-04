from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ReconciliationCheck:
    name: str
    ok: bool
    level: str
    detail: str


@dataclass(frozen=True)
class WorkflowCheckpointReconciliationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: list[ReconciliationCheck] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "checks": [
                {
                    "name": check.name,
                    "ok": check.ok,
                    "level": check.level,
                    "detail": check.detail,
                }
                for check in self.checks
            ],
            "metadata": dict(self.metadata),
        }


class WorkflowCheckpointReconciliationService:
    def __init__(
        self,
        *,
        message_repo,
        agent_run_repo,
        execution_repo,
    ) -> None:
        self.message_repo = message_repo
        self.agent_run_repo = agent_run_repo
        self.execution_repo = execution_repo

    def reconcile(self, workflow_run) -> WorkflowCheckpointReconciliationResult:
        state = dict(getattr(workflow_run, "state", None) or {})
        session_id = getattr(workflow_run, "session_id", None) or state.get("session_id")
        checks: list[ReconciliationCheck] = []

        if not session_id:
            checks.append(
                ReconciliationCheck(
                    name="session_id_present",
                    ok=False,
                    level="error",
                    detail="workflow_run.session_id is missing",
                )
            )
            return self._result(workflow_run, state, checks)

        messages = self.message_repo.list_by_session_id(session_id)
        message_by_id = {
            message.id: message
            for message in messages
            if getattr(message, "status", "normal") != "deleted"
        }
        execution = self.execution_repo.get_latest_by_session_id(session_id)

        checks.append(self._thread_id_check(workflow_run, state))
        checks.append(
            self._message_exists_check(
                name="last_user_message_exists",
                state=state,
                key="last_user_message_id",
                role_type="user",
                message_type="answer",
                message_by_id=message_by_id,
            )
        )
        checks.append(
            self._message_exists_check(
                name="last_assistant_message_exists",
                state=state,
                key="last_assistant_message_id",
                role_type="assistant",
                message_type=None,
                message_by_id=message_by_id,
            )
        )
        checks.append(
            self._agent_run_exists_check(
                name="last_topic_judge_agent_run_exists",
                state=state,
                key="last_topic_judge_agent_run_id",
            )
        )
        checks.append(
            self._agent_run_exists_check(
                name="last_followup_agent_run_exists",
                state=state,
                key="last_followup_agent_run_id",
            )
        )
        checks.append(self._advance_execution_marker_check(state, execution))
        checks.append(self._failed_state_check(workflow_run, state))

        return self._result(workflow_run, state, checks)

    def _thread_id_check(self, workflow_run, state: dict) -> ReconciliationCheck:
        workflow_thread_id = getattr(workflow_run, "thread_id", None)
        state_thread_id = state.get("thread_id")
        if not state_thread_id:
            return ReconciliationCheck(
                name="thread_id_aligned",
                ok=False,
                level="warning",
                detail="state.thread_id is missing",
            )
        if workflow_thread_id != state_thread_id:
            return ReconciliationCheck(
                name="thread_id_aligned",
                ok=False,
                level="error",
                detail=(
                    f"workflow_run.thread_id={workflow_thread_id} "
                    f"does not match state.thread_id={state_thread_id}"
                ),
            )
        return ReconciliationCheck(
            name="thread_id_aligned",
            ok=True,
            level="info",
            detail=f"thread_id {workflow_thread_id} is aligned",
        )

    def _message_exists_check(
        self,
        *,
        name: str,
        state: dict,
        key: str,
        role_type: str,
        message_type: str | None,
        message_by_id: dict[int, Any],
    ) -> ReconciliationCheck:
        message_id = state.get(key)
        if not message_id:
            return ReconciliationCheck(
                name=name,
                ok=True,
                level="info",
                detail=f"{key} is not present",
            )
        message = message_by_id.get(message_id)
        if not message:
            return ReconciliationCheck(
                name=name,
                ok=False,
                level="error",
                detail=f"{key}={message_id} is missing from interview_messages",
            )
        if getattr(message, "role_type", None) != role_type:
            return ReconciliationCheck(
                name=name,
                ok=False,
                level="error",
                detail=f"{key}={message_id} has role_type={getattr(message, 'role_type', None)}",
            )
        if message_type and getattr(message, "message_type", None) != message_type:
            return ReconciliationCheck(
                name=name,
                ok=False,
                level="error",
                detail=(
                    f"{key}={message_id} has "
                    f"message_type={getattr(message, 'message_type', None)}"
                ),
            )
        return ReconciliationCheck(
            name=name,
            ok=True,
            level="info",
            detail=f"{key}={message_id} exists",
        )

    def _agent_run_exists_check(
        self,
        *,
        name: str,
        state: dict,
        key: str,
    ) -> ReconciliationCheck:
        agent_run_id = state.get(key)
        if not agent_run_id:
            return ReconciliationCheck(
                name=name,
                ok=True,
                level="info",
                detail=f"{key} is not present",
            )
        agent_run = self.agent_run_repo.get_by_id(agent_run_id)
        if not agent_run:
            return ReconciliationCheck(
                name=name,
                ok=False,
                level="error",
                detail=f"{key}={agent_run_id} is missing from agent_runs",
            )
        return ReconciliationCheck(
            name=name,
            ok=True,
            level="info",
            detail=f"{key}={agent_run_id} exists",
        )

    def _advance_execution_marker_check(
        self,
        state: dict,
        execution,
    ) -> ReconciliationCheck:
        completed_steps = state.get("completed_steps") or []
        if "advance_execution" not in completed_steps and "advance_execution_reused" not in completed_steps:
            return ReconciliationCheck(
                name="advance_execution_marker_exists",
                ok=True,
                level="info",
                detail="advance_execution is not marked completed",
            )

        answer_message_id = state.get("last_user_message_id")
        if not answer_message_id:
            return ReconciliationCheck(
                name="advance_execution_marker_exists",
                ok=False,
                level="warning",
                detail="advance_execution completed but last_user_message_id is missing",
            )
        if not execution:
            return ReconciliationCheck(
                name="advance_execution_marker_exists",
                ok=False,
                level="warning",
                detail="advance_execution completed but no execution artifact was found",
            )
        if self._execution_has_answer_marker(execution, answer_message_id):
            return ReconciliationCheck(
                name="advance_execution_marker_exists",
                ok=True,
                level="info",
                detail=f"execution contains answer_message_id={answer_message_id}",
            )
        return ReconciliationCheck(
            name="advance_execution_marker_exists",
            ok=False,
            level="warning",
            detail=f"execution does not contain answer_message_id={answer_message_id}",
        )

    def _failed_state_check(self, workflow_run, state: dict) -> ReconciliationCheck:
        status = getattr(workflow_run, "status", None)
        if status != "failed":
            return ReconciliationCheck(
                name="failed_workflow_has_error",
                ok=True,
                level="info",
                detail=f"workflow status is {status}",
            )
        last_error = getattr(workflow_run, "last_error", None) or state.get("last_error")
        if not last_error:
            return ReconciliationCheck(
                name="failed_workflow_has_error",
                ok=False,
                level="error",
                detail="workflow status is failed but last_error is missing",
            )
        current_step = getattr(workflow_run, "current_step", None)
        error_step = last_error.get("step_id") if isinstance(last_error, dict) else None
        if error_step and current_step and current_step != error_step:
            return ReconciliationCheck(
                name="failed_workflow_has_error",
                ok=False,
                level="warning",
                detail=f"current_step={current_step} differs from last_error.step_id={error_step}",
            )
        return ReconciliationCheck(
            name="failed_workflow_has_error",
            ok=True,
            level="info",
            detail="failed workflow has last_error",
        )

    def _execution_has_answer_marker(self, execution, answer_message_id: int) -> bool:
        state = getattr(execution, "state", None) or {}
        for section in state.get("sections") or []:
            for evidence in section.get("evidence") or []:
                if evidence.get("answer_message_id") == answer_message_id:
                    return True
        return False

    def _result(
        self,
        workflow_run,
        state: dict,
        checks: list[ReconciliationCheck],
    ) -> WorkflowCheckpointReconciliationResult:
        errors = [check.detail for check in checks if not check.ok and check.level == "error"]
        warnings = [check.detail for check in checks if not check.ok and check.level == "warning"]
        return WorkflowCheckpointReconciliationResult(
            ok=not errors,
            errors=errors,
            warnings=warnings,
            checks=checks,
            metadata={
                "workflow_run_id": getattr(workflow_run, "workflow_run_id", None),
                "thread_id": getattr(workflow_run, "thread_id", None),
                "status": getattr(workflow_run, "status", None),
                "current_step": getattr(workflow_run, "current_step", None),
                "state_thread_id": state.get("thread_id"),
                "completed_steps": state.get("completed_steps") or [],
                "failed_steps": state.get("failed_steps") or [],
            },
        )
