from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from inspect import isawaitable
from typing import Any, TypeVar

from app.config.settings import settings


ResultT = TypeVar("ResultT")


class WorkflowStepTimeoutError(TimeoutError):
    pass


@dataclass(frozen=True)
class WorkflowStepPolicy:
    max_attempts: int = settings.workflow_step_max_attempts
    timeout_seconds: float = settings.workflow_step_timeout_seconds


class WorkflowStepRunner:
    def __init__(
        self,
        policy: WorkflowStepPolicy | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.policy = policy or WorkflowStepPolicy()
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    async def run(
        self,
        state: dict[str, Any],
        step_id: str,
        call: Callable[[], ResultT | Awaitable[ResultT]],
        *,
        timeout_seconds: float | None = None,
        max_attempts: int | None = None,
    ) -> ResultT:
        attempts = max(1, max_attempts or self.policy.max_attempts)
        last_exc: Exception | None = None
        for attempt_no in range(1, attempts + 1):
            self._record_attempt_start(state, step_id, attempt_no)
            try:
                result = call()
                if isawaitable(result):
                    result = await asyncio.wait_for(
                        result,
                        timeout=timeout_seconds or self.policy.timeout_seconds,
                    )
                self._record_attempt_success(state, step_id, attempt_no)
                return result
            except asyncio.TimeoutError as exc:
                last_exc = WorkflowStepTimeoutError(
                    f"workflow step timed out after {timeout_seconds or self.policy.timeout_seconds} seconds"
                )
                self._record_attempt_failure(state, step_id, attempt_no, last_exc)
            except Exception as exc:
                last_exc = exc
                self._record_attempt_failure(state, step_id, attempt_no, exc)
            if attempt_no < attempts:
                state["retrying_step"] = step_id
                state["retry_attempt_no"] = attempt_no + 1
        state.pop("retrying_step", None)
        state.pop("retry_attempt_no", None)
        raise last_exc or RuntimeError(f"workflow step failed: {step_id}")

    def _record_attempt_start(
        self,
        state: dict[str, Any],
        step_id: str,
        attempt_no: int,
    ) -> None:
        step_state = self._step_state(state, step_id)
        step_state["status"] = "running"
        step_state["attempts"] = attempt_no
        step_state["started_at"] = self._timestamp()
        step_state.pop("last_error", None)

    def _record_attempt_success(
        self,
        state: dict[str, Any],
        step_id: str,
        attempt_no: int,
    ) -> None:
        step_state = self._step_state(state, step_id)
        step_state["status"] = "success"
        step_state["attempts"] = attempt_no
        step_state["finished_at"] = self._timestamp()
        step_state.pop("last_error", None)
        state.pop("retrying_step", None)
        state.pop("retry_attempt_no", None)

    def _record_attempt_failure(
        self,
        state: dict[str, Any],
        step_id: str,
        attempt_no: int,
        exc: Exception,
    ) -> None:
        step_state = self._step_state(state, step_id)
        step_state["status"] = "failed"
        step_state["attempts"] = attempt_no
        step_state["finished_at"] = self._timestamp()
        step_state["last_error"] = {
            "message": str(exc),
            "error_type": exc.__class__.__name__,
            "attempt_no": attempt_no,
        }

    def _step_state(self, state: dict[str, Any], step_id: str) -> dict[str, Any]:
        steps = state.setdefault("step_execution", {})
        if not isinstance(steps, dict):
            steps = {}
            state["step_execution"] = steps
        step_state = steps.setdefault(step_id, {})
        if not isinstance(step_state, dict):
            step_state = {}
            steps[step_id] = step_state
        return step_state

    def _timestamp(self) -> str:
        return self.clock().isoformat()
