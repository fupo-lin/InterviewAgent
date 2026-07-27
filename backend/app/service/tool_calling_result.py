from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ToolCallingPayload:
    mode: str
    available_tools: list[str] = field(default_factory=list)
    trace: list[dict[str, Any]] = field(default_factory=list)
    responses: list[dict[str, Any]] = field(default_factory=list)
    tool_budget_exhausted: bool = False

    def to_raw_response(self, **extra: Any) -> dict[str, Any]:
        payload = asdict(self)
        if not self.tool_budget_exhausted:
            payload.pop("tool_budget_exhausted", None)
        return {"tool_calling": {**payload, **extra}}


def tool_calling_trace(raw_response: dict | None) -> list[dict[str, Any]]:
    if not isinstance(raw_response, dict):
        return []

    direct_trace = _trace_from_payload(raw_response.get("tool_calling"))
    if direct_trace:
        return direct_trace

    original = raw_response.get("original")
    if isinstance(original, dict):
        return _trace_from_payload(original.get("tool_calling"))
    return []


def _trace_from_payload(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    trace = payload.get("trace")
    if not isinstance(trace, list):
        return []
    return [item for item in trace if isinstance(item, dict)]
