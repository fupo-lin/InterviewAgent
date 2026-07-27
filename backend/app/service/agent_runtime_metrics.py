from __future__ import annotations

from typing import Any

from app.service.tool_calling_result import tool_calling_trace


def build_agent_runtime_metrics(
    *,
    raw_response: dict | None,
    latency_ms: int,
    status: str,
    error: Exception | None = None,
) -> dict[str, Any]:
    trace = tool_calling_trace(raw_response)
    token_usage = _token_usage(raw_response)
    metrics: dict[str, Any] = {
        "status": status,
        "latency_ms": max(int(latency_ms), 0),
        "tool_call_count": len(trace),
        "tool_round_count": _tool_round_count(raw_response, trace),
        "tool_names": _tool_names(trace),
        "tool_error_count": _tool_error_count(trace),
        "tool_budget_exhausted": _tool_budget_exhausted(raw_response),
        "model_response_count": _model_response_count(raw_response),
        "token_usage_available": token_usage is not None,
    }
    if token_usage is not None:
        metrics["token_usage"] = token_usage
    if error is not None:
        metrics["error_type"] = error.__class__.__name__
    return metrics


def _token_usage(raw_response: dict | None) -> dict[str, int] | None:
    usages = list(_usage_dicts(raw_response))
    if not usages:
        return None

    totals: dict[str, int] = {"source_count": len(usages)}
    for usage in usages:
        for source_key, target_key in (
            ("prompt_tokens", "prompt_tokens"),
            ("input_tokens", "prompt_tokens"),
            ("completion_tokens", "completion_tokens"),
            ("output_tokens", "completion_tokens"),
            ("total_tokens", "total_tokens"),
        ):
            value = _int_or_none(usage.get(source_key))
            if value is not None:
                totals[target_key] = totals.get(target_key, 0) + value
    return totals


def _usage_dicts(value: Any):
    if isinstance(value, dict):
        usage = value.get("usage")
        if isinstance(usage, dict):
            yield usage
        tool_calling = value.get("tool_calling")
        if isinstance(tool_calling, dict):
            for response in tool_calling.get("responses") or []:
                yield from _usage_dicts(response)
        for key in ("original", "repair"):
            yield from _usage_dicts(value.get(key))
    elif isinstance(value, list):
        for item in value:
            yield from _usage_dicts(item)


def _tool_round_count(raw_response: dict | None, trace: list[dict[str, Any]]) -> int:
    responses = _tool_calling_responses(raw_response)
    count = 0
    for response in responses:
        message = _choice_message(response)
        if message and message.get("tool_calls"):
            count += 1
    if count == 0 and trace:
        return 1
    return count


def _model_response_count(raw_response: dict | None) -> int:
    responses = _tool_calling_responses(raw_response)
    if responses:
        return len(responses)
    return 1 if isinstance(raw_response, dict) else 0


def _tool_calling_responses(raw_response: dict | None) -> list[dict]:
    payloads = []
    if isinstance(raw_response, dict):
        direct = raw_response.get("tool_calling")
        if isinstance(direct, dict):
            payloads.append(direct)
        original = raw_response.get("original")
        if isinstance(original, dict) and isinstance(original.get("tool_calling"), dict):
            payloads.append(original["tool_calling"])

    responses = []
    for payload in payloads:
        for item in payload.get("responses") or []:
            if isinstance(item, dict):
                responses.append(item)
    return responses


def _choice_message(response: dict) -> dict | None:
    choices = response.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return None
    message = choices[0].get("message")
    return message if isinstance(message, dict) else None


def _tool_names(trace: list[dict[str, Any]]) -> list[str]:
    names = []
    for item in trace:
        name = str(item.get("tool_name") or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def _tool_error_count(trace: list[dict[str, Any]]) -> int:
    count = 0
    for item in trace:
        result = item.get("result")
        if isinstance(result, dict) and result.get("status") not in {None, "success"}:
            count += 1
    return count


def _tool_budget_exhausted(raw_response: dict | None) -> bool:
    if not isinstance(raw_response, dict):
        return False
    tool_calling = raw_response.get("tool_calling")
    if isinstance(tool_calling, dict) and bool(tool_calling.get("tool_budget_exhausted")):
        return True
    original = raw_response.get("original")
    if isinstance(original, dict):
        tool_calling = original.get("tool_calling")
        return isinstance(tool_calling, dict) and bool(tool_calling.get("tool_budget_exhausted"))
    return False


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
