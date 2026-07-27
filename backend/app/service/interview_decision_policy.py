from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class DecisionPolicyInput:
    topic_judge_result: dict | None
    execution_state: dict
    current_section: dict
    current_section_index: int
    section_count: int
    completed_rounds: int
    target_rounds: int
    open_threads: list[dict]
    recent_history: list[Any] | None = None
    retrieved_evidence: list[Any] | str | None = None


@dataclass(frozen=True)
class DecisionPolicyResult:
    final_action: str
    reason: str
    conflict_resolution: str | None = None
    source: str = "decision_policy"
    confidence: str = "medium"

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


class CodeDecisionPolicy:
    """
    Deterministic first version of the runtime decision policy.

    The workflow still owns the graph, but section progression is no longer an
    implicit hard rule buried in InterviewExecutionService. This class is the
    replacement point for a future LLM-backed policy.
    """

    def decide(self, policy_input: DecisionPolicyInput) -> DecisionPolicyResult:
        judge = policy_input.topic_judge_result or {}
        requested_action = judge.get("next_action")
        requested_reason = judge.get("reason") or ""
        confidence = str(judge.get("confidence") or "medium")
        has_next_section = policy_input.current_section_index + 1 < policy_input.section_count
        target_reached = policy_input.completed_rounds >= max(policy_input.target_rounds, 1)
        active_threads = self._active_threads_for_section(
            policy_input.open_threads,
            policy_input.current_section,
        )
        has_high_value_thread = any(
            item.get("priority") == "high" for item in active_threads
        )
        has_supporting_evidence = self._has_supporting_evidence(policy_input.retrieved_evidence)
        has_recent_answer = self._has_recent_candidate_answer(policy_input.recent_history)

        if requested_action == "finished":
            return DecisionPolicyResult(
                final_action="finished",
                reason=requested_reason or "topic_judge_requested_finished",
                source="topic_judge",
                confidence=confidence,
            )

        if requested_action == "wrap_up_interview":
            if has_next_section:
                return DecisionPolicyResult(
                    final_action="move_next_section",
                    reason=(
                        requested_reason
                        or "judge_requested_wrap_up_before_remaining_sections"
                    ),
                    conflict_resolution="wrap_up_requested_before_last_section",
                    confidence=confidence,
                )
            return DecisionPolicyResult(
                final_action="wrap_up_interview",
                reason=requested_reason or "topic_judge_requested_wrap_up",
                source="topic_judge",
                confidence=confidence,
            )

        if requested_action == "move_next_section":
            if active_threads and (has_high_value_thread or has_supporting_evidence):
                return DecisionPolicyResult(
                    final_action="continue_current_topic",
                    reason=(
                        requested_reason
                        or "high_value_open_thread_before_section_transition"
                    ),
                    conflict_resolution="open_thread_overrode_move_next_section",
                    confidence=confidence,
                )
            if has_next_section:
                return DecisionPolicyResult(
                    final_action="move_next_section",
                    reason=requested_reason or "topic_judge_requested_move_next_section",
                    source="topic_judge",
                    confidence=confidence,
                )
            return DecisionPolicyResult(
                final_action="wrap_up_interview",
                reason=requested_reason or "last_section_completed",
                conflict_resolution="move_next_requested_without_next_section",
                confidence=confidence,
            )

        if requested_action in {"continue_current_topic", "switch_topic_in_section"}:
            if target_reached and not active_threads:
                return DecisionPolicyResult(
                    final_action=self._next_section_or_wrap_up(has_next_section),
                    reason=(
                        requested_reason
                        or "target_rounds_reached_without_open_threads"
                    ),
                    conflict_resolution=(
                        "target_rounds_reached_overrode_continue_without_open_threads"
                    ),
                    confidence=confidence,
                )
            return DecisionPolicyResult(
                final_action=requested_action,
                reason=requested_reason or "topic_judge_requested_continue",
                source="topic_judge",
                confidence=confidence,
            )

        if target_reached and not active_threads:
            return DecisionPolicyResult(
                final_action=self._next_section_or_wrap_up(has_next_section),
                reason="target_rounds_reached_without_open_threads",
                conflict_resolution="policy_default_target_rounds",
                confidence=confidence,
            )

        if active_threads and (has_high_value_thread or has_supporting_evidence):
            return DecisionPolicyResult(
                final_action="continue_current_topic",
                reason="active_open_thread_with_supporting_evidence",
                conflict_resolution="policy_prioritized_open_thread",
                confidence=confidence,
            )

        if not has_recent_answer:
            return DecisionPolicyResult(
                final_action="continue_current_topic",
                reason="no_recent_candidate_answer_context",
                conflict_resolution="policy_requires_recent_answer_before_transition",
                confidence=confidence,
            )

        if policy_input.current_section.get("uncovered_probe_points"):
            return DecisionPolicyResult(
                final_action="switch_topic_in_section",
                reason="current_section_has_uncovered_probe_points",
                source="fallback",
                confidence=confidence,
            )

        return DecisionPolicyResult(
            final_action="continue_current_topic",
            reason="continue_current_topic_by_policy_default",
            source="fallback",
            confidence=confidence,
        )

    def _next_section_or_wrap_up(self, has_next_section: bool) -> str:
        return "move_next_section" if has_next_section else "wrap_up_interview"

    def _active_threads_for_section(
        self,
        open_threads: list[dict],
        current_section: dict,
    ) -> list[dict]:
        section_key = current_section.get("section_key")
        active = []
        for item in open_threads or []:
            if not isinstance(item, dict):
                continue
            if item.get("status") and item.get("status") != "open":
                continue
            if item.get("section_key") and item.get("section_key") != section_key:
                continue
            active.append(item)
        return active

    def _has_supporting_evidence(self, retrieved_evidence: list[Any] | str | None) -> bool:
        if not retrieved_evidence:
            return False
        if isinstance(retrieved_evidence, str):
            return bool(retrieved_evidence.strip())
        if isinstance(retrieved_evidence, list):
            return any(bool(self._evidence_content(item)) for item in retrieved_evidence)
        return False

    def _evidence_content(self, item: Any) -> str:
        if isinstance(item, dict):
            return str(item.get("content") or item.get("content_excerpt") or "")
        return str(getattr(item, "content", "") or getattr(item, "content_excerpt", ""))

    def _has_recent_candidate_answer(self, recent_history: list[Any] | None) -> bool:
        if not recent_history:
            return False
        for item in recent_history:
            role_type = item.get("role_type") if isinstance(item, dict) else getattr(item, "role_type", None)
            content = item.get("content") if isinstance(item, dict) else getattr(item, "content", None)
            if role_type == "user" and str(content or "").strip():
                return True
        return False
