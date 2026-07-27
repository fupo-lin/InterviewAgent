from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.service.interview_runtime_state import InterviewRuntimeState


@dataclass(frozen=True)
class InterviewRuntimeRoute:
    route: str
    reason: str


class InterviewRuntimeRouter:
    CONTINUE_TOPIC = "continue_topic"
    SWITCH_TOPIC = "switch_topic"
    MOVE_NEXT_SECTION = "move_next_section"
    WRAP_UP = "wrap_up"
    FINISHED = "finished"

    def route_after_advance(
        self,
        state: InterviewRuntimeState,
        execution: Any,
    ) -> InterviewRuntimeRoute:
        execution_status = getattr(execution, "status", None)
        if execution_status == "finished":
            return InterviewRuntimeRoute(
                route=self.FINISHED,
                reason="execution_status_finished",
            )

        next_action = self._next_action(state, execution)
        if next_action == "finished":
            return InterviewRuntimeRoute(
                route=self.FINISHED,
                reason="next_action_finished",
            )
        if next_action == "wrap_up_interview":
            return InterviewRuntimeRoute(
                route=self.WRAP_UP,
                reason="next_action_wrap_up_interview",
            )
        if next_action == "move_next_section":
            return InterviewRuntimeRoute(
                route=self.MOVE_NEXT_SECTION,
                reason="next_action_move_next_section",
            )
        if next_action == "switch_topic_in_section":
            return InterviewRuntimeRoute(
                route=self.SWITCH_TOPIC,
                reason="next_action_switch_topic_in_section",
            )
        return InterviewRuntimeRoute(
            route=self.CONTINUE_TOPIC,
            reason="default_continue_current_topic",
        )

    def _next_action(self, state: InterviewRuntimeState, execution: Any) -> str | None:
        state_action = state.get("next_action")
        if isinstance(state_action, str) and state_action:
            return state_action

        execution_state = getattr(execution, "state", None) or {}
        execution_action = execution_state.get("next_action") or {}
        if isinstance(execution_action, dict):
            return execution_action.get("type")
        if isinstance(execution_action, str):
            return execution_action
        return None
