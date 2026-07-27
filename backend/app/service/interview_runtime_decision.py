from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.service.interview_runtime_router import InterviewRuntimeRoute


@dataclass(frozen=True)
class RuntimeDecision:
    action: str
    route: str
    source: str
    reason: str
    conflict_resolution: str | None = None
    confidence: str = "medium"
    suggested_probe_point: str | None = None
    force_reason: str | None = None
    created_at_step: str = "advance_execution"

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


def runtime_decision_from_route(
    *,
    state: dict,
    execution: Any,
    route_decision: InterviewRuntimeRoute,
) -> dict[str, Any]:
    execution_state = getattr(execution, "state", None) or {}
    next_action = execution_state.get("next_action") or {}
    last_judge = execution_state.get("last_topic_judge") or {}
    policy = execution_state.get("decision_policy") or {}
    current_section = _current_section(execution)
    action = policy.get("final_action") or _next_action_type(next_action) or _action_from_route(route_decision.route)
    source = policy.get("source") or _decision_source(next_action, last_judge)
    decision = RuntimeDecision(
        action=action,
        route=route_decision.route,
        source=source,
        reason=policy.get("reason") or _next_action_reason(next_action) or route_decision.reason,
        conflict_resolution=policy.get("conflict_resolution"),
        confidence=str(policy.get("confidence") or last_judge.get("confidence") or "medium"),
        suggested_probe_point=_suggested_probe_point(current_section),
        force_reason=next_action.get("force_reason") if isinstance(next_action, dict) else None,
    )
    payload = decision.to_dict()
    state["runtime_decision"] = payload
    return payload


def _next_action_type(next_action: Any) -> str | None:
    if isinstance(next_action, dict):
        return next_action.get("type")
    if isinstance(next_action, str):
        return next_action
    return None


def _next_action_reason(next_action: Any) -> str | None:
    if isinstance(next_action, dict):
        return next_action.get("reason")
    return None


def _decision_source(next_action: Any, last_judge: dict) -> str:
    if isinstance(next_action, dict) and next_action.get("decision_source"):
        return str(next_action["decision_source"])
    if last_judge.get("next_action"):
        return "topic_judge"
    return "fallback"


def _action_from_route(route: str) -> str:
    return {
        "continue_topic": "continue_current_topic",
        "switch_topic": "switch_topic_in_section",
        "move_next_section": "move_next_section",
        "wrap_up": "wrap_up_interview",
        "finished": "finished",
    }.get(route, "continue_current_topic")


def _current_section(execution: Any) -> dict:
    state = getattr(execution, "state", None) or {}
    sections = state.get("sections") or []
    index = int(getattr(execution, "current_section_index", 0) or 0)
    if 0 <= index < len(sections):
        return sections[index] or {}
    return {}


def _suggested_probe_point(section: dict) -> str | None:
    uncovered = section.get("uncovered_probe_points") or []
    if uncovered:
        return str(uncovered[0])
    probe_points = section.get("probe_points") or []
    if probe_points:
        return str(probe_points[-1])
    return None
