from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


ACTIONABLE_MEMORY_TYPES = {
    "open_followup",
    "technical_highlight",
    "project_claim",
    "missing_detail",
    "risk_signal",
}


@dataclass(frozen=True)
class RuntimeMemoryItem:
    id: str
    memory_type: str
    content: str
    source_message_id: int | None = None
    source_agent_run_id: int | None = None
    round_no: int | None = None
    section_key: str | None = None
    topic_key: str | None = None
    probe_point: str | None = None
    highlight: str = ""
    missing_detail: str = ""
    priority: str = "medium"
    status: str = "open"
    confidence: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value not in (None, "")}


def normalize_runtime_memory_item(
    *,
    item: Any,
    memory_type: str,
    index: int,
    answer_message,
    current_section: dict,
    source_field: str,
    agent_run_id: int | None = None,
) -> dict[str, Any]:
    payload = item if isinstance(item, dict) else {"content": str(item)}
    highlight = _first_text(
        payload,
        "highlight",
        "claim",
        "label",
        "content",
        "evidence",
    )
    missing_detail = _first_text(
        payload,
        "missing_detail",
        "missing_followup",
        "followup_gap",
        "next_question_intent",
        "suggestion",
    )
    content = _first_non_empty(
        payload.get("content"),
        highlight,
        missing_detail,
    )
    source_message_id = _int_or_none(
        payload.get("source_message_id") or getattr(answer_message, "id", None)
    )
    round_no = _int_or_none(payload.get("round_no") or getattr(answer_message, "round_no", None))
    section_key = payload.get("section_key") or current_section.get("section_key")
    probe_point = (
        payload.get("probe_point")
        or payload.get("related_probe_point")
        or _first_probe_point(current_section)
    )
    normalized_type = _memory_type(payload.get("memory_type") or memory_type)
    metadata = dict(payload.get("metadata") or {})
    metadata.update(
        {
            "source_field": source_field,
            "raw_memory_type": payload.get("memory_type") or memory_type,
        }
    )
    memory_item = RuntimeMemoryItem(
        id=str(
            payload.get("id")
            or _memory_id(
                memory_type=normalized_type,
                source_message_id=source_message_id,
                probe_point=probe_point,
                index=index,
            )
        ),
        memory_type=normalized_type,
        content=str(content),
        source_message_id=source_message_id,
        source_agent_run_id=_int_or_none(payload.get("source_agent_run_id") or agent_run_id),
        round_no=round_no,
        section_key=str(section_key) if section_key else None,
        topic_key=str(payload.get("topic_key") or section_key or "") or None,
        probe_point=str(probe_point) if probe_point else None,
        highlight=str(highlight),
        missing_detail=str(missing_detail),
        priority=str(payload.get("priority") or "medium"),
        status=str(payload.get("status") or "open"),
        confidence=str(payload.get("confidence") or "unknown"),
        metadata=metadata,
    )
    return memory_item.to_dict()


def is_actionable_memory_item(item: dict[str, Any]) -> bool:
    if not isinstance(item, dict):
        return False
    if item.get("status") == "closed":
        return False
    return str(item.get("memory_type") or "open_followup") in ACTIONABLE_MEMORY_TYPES


def ensure_runtime_memory_item_shape(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    shaped = dict(item)
    shaped["memory_type"] = _memory_type(shaped.get("memory_type") or "open_followup")
    shaped["content"] = _first_non_empty(
        shaped.get("content"),
        shaped.get("highlight"),
        shaped.get("missing_detail"),
    )
    shaped["highlight"] = str(shaped.get("highlight") or shaped.get("content") or "")
    shaped["missing_detail"] = str(shaped.get("missing_detail") or "")
    shaped["priority"] = str(shaped.get("priority") or "medium")
    shaped["status"] = str(shaped.get("status") or "open")
    shaped["confidence"] = str(shaped.get("confidence") or "unknown")
    shaped["metadata"] = dict(shaped.get("metadata") or {})
    if not shaped.get("id"):
        shaped["id"] = _memory_id(
            memory_type=shaped["memory_type"],
            source_message_id=shaped.get("source_message_id"),
            probe_point=shaped.get("probe_point"),
            index=1,
        )
    return shaped


def memory_identity(item: dict[str, Any]) -> tuple[Any, Any, Any, Any]:
    return (
        item.get("source_message_id"),
        item.get("memory_type") or "open_followup",
        item.get("content") or item.get("highlight"),
        item.get("probe_point"),
    )


def _memory_type(value: Any) -> str:
    text = str(value or "open_followup").strip() or "open_followup"
    return text.lower().replace(" ", "_")


def _memory_id(
    *,
    memory_type: str,
    source_message_id: int | None,
    probe_point: Any,
    index: int,
) -> str:
    parts = [
        "memory",
        _id_part(memory_type),
        _id_part(source_message_id or "message"),
        _id_part(probe_point or "topic"),
        str(index),
    ]
    return ":".join(parts)


def _id_part(value: Any) -> str:
    text = str(value)
    cleaned = []
    for char in text:
        if char.isalnum():
            cleaned.append(char.lower())
        else:
            cleaned.append("_")
    return "".join(cleaned).strip("_") or "unknown"


def _first_text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if str(value or "").strip():
            return str(value)
    return ""


def _first_non_empty(*values: Any) -> str:
    for value in values:
        if str(value or "").strip():
            return str(value)
    return ""


def _first_probe_point(section: dict) -> str | None:
    uncovered = section.get("uncovered_probe_points") or []
    if uncovered:
        return str(uncovered[0])
    probes = section.get("probe_points") or []
    if probes:
        return str(probes[0])
    return None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
