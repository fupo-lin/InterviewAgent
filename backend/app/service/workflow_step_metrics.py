from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def record_workflow_step_metric(
    state: dict[str, Any],
    *,
    step_id: str,
    status: str,
    latency_ms: int,
    current_step: str,
    error: Exception | None = None,
    last_error: dict | None = None,
) -> None:
    metrics = list(state.get("step_metrics") or [])
    item: dict[str, Any] = {
        "step_id": step_id,
        "status": status,
        "latency_ms": max(int(latency_ms), 0),
        "current_step": current_step,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    error_payload = last_error or {}
    if error is not None:
        item["error_type"] = error.__class__.__name__
        item["error_message"] = str(error)
    elif status == "failed" and error_payload:
        item["error_type"] = error_payload.get("error_type")
        item["error_message"] = error_payload.get("message")

    metrics.append(item)
    state["step_metrics"] = metrics
    state["last_step_metric"] = item


def step_metrics_summary(state: dict[str, Any]) -> dict[str, Any]:
    metrics = [item for item in state.get("step_metrics") or [] if isinstance(item, dict)]
    failed = [item for item in metrics if item.get("status") == "failed"]
    return {
        "step_count": len(metrics),
        "failed_step_count": len(failed),
        "total_latency_ms": sum(int(item.get("latency_ms") or 0) for item in metrics),
        "last_step_id": metrics[-1].get("step_id") if metrics else None,
    }
