from __future__ import annotations

from app.repository.interview_repository import InterviewPlanExecutionRepository
from app.service.interview_decision_policy import CodeDecisionPolicy, DecisionPolicyInput


class InterviewExecutionService:
    def __init__(
        self,
        execution_repo: InterviewPlanExecutionRepository,
        decision_policy=None,
    ):
        self.execution_repo = execution_repo
        self.decision_policy = decision_policy or CodeDecisionPolicy()

    def initialize(self, session_id: int, interview_plan_id: int, plan_content: dict):
        state = self._initial_state(plan_content)
        current_section = self._section_at(state, 0)
        return self.execution_repo.create(
            session_id=session_id,
            interview_plan_id=interview_plan_id,
            current_section_key=current_section.get("section_key") if current_section else None,
            current_section_index=0,
            state=state,
        )

    def get_latest(self, session_id: int):
        return self.execution_repo.get_latest_by_session_id(session_id)

    def current_section(self, execution) -> dict | None:
        if not execution:
            return None
        return self._section_at(execution.state or {}, execution.current_section_index)

    def advance_after_answer(
        self,
        execution,
        answer: str,
        round_no: int,
        judge_result: dict | None = None,
        open_threads: list[dict] | None = None,
        recent_history: list | None = None,
        retrieved_evidence=None,
    ):
        if not execution or execution.status != "active":
            return None

        state = execution.state or {}
        sections = state.get("sections") or []
        current_index = execution.current_section_index
        current_section = self._section_at(state, current_index)
        if not current_section:
            self._mark_wrap_up(execution, state, "no_active_section")
            return execution

        current_section["completed_rounds"] = int(current_section.get("completed_rounds") or 0) + 1
        probe_point = self._current_probe_point(current_section)
        covered_probe_points = self._judge_covered_probe_points(current_section, judge_result)
        current_section.setdefault("evidence", []).append(
            {
                "round_no": round_no,
                "answer_excerpt": answer[:300],
                "probe_point": probe_point,
                "covered_probe_points": covered_probe_points,
                "answer_quality": (judge_result or {}).get("answer_quality", "unknown"),
                "confidence": (judge_result or {}).get("confidence", "unknown"),
                "judge_reason": (judge_result or {}).get("reason", ""),
                "technical_highlights": (judge_result or {}).get("technical_highlights", []),
                "open_threads": (judge_result or {}).get("open_threads", []),
            }
        )
        self._mark_probe_points_covered(current_section, covered_probe_points)

        execution.total_completed_round_no = int(execution.total_completed_round_no or 0) + 1
        target_rounds = int(current_section.get("target_rounds") or 1)
        state["last_topic_judge"] = judge_result or {}
        policy_result = self.decision_policy.decide(
            DecisionPolicyInput(
                topic_judge_result=judge_result,
                execution_state=state,
                current_section=current_section,
                current_section_index=current_index,
                section_count=len(sections),
                completed_rounds=current_section["completed_rounds"],
                target_rounds=target_rounds,
                open_threads=open_threads or (judge_result or {}).get("open_threads") or [],
                recent_history=recent_history,
                retrieved_evidence=retrieved_evidence,
            )
        )
        state["decision_policy"] = policy_result.to_dict()

        if policy_result.final_action == "finished":
            current_section["status"] = "completed"
            current_section["completion_reason"] = policy_result.reason
            execution.status = "finished"
            state["next_action"] = {
                "type": "finished",
                "decision_source": policy_result.source,
                "conflict_resolution": policy_result.conflict_resolution,
                "reason": policy_result.reason,
            }
        elif policy_result.final_action == "wrap_up_interview":
            current_section["status"] = "completed"
            current_section["completion_reason"] = policy_result.reason
            self._mark_wrap_up(execution, state, policy_result.reason)
        elif policy_result.final_action == "move_next_section":
            self._move_next_section(
                execution=execution,
                state=state,
                sections=sections,
                current_section=current_section,
                current_index=current_index,
                reason=policy_result.reason,
                decision_source=policy_result.source,
                conflict_resolution=policy_result.conflict_resolution,
            )
        else:
            execution.current_section_round_no = int(execution.current_section_round_no or 0) + 1
            state["next_action"] = self._next_action_for_policy(
                current_section,
                judge_result,
                policy_result,
            )

        execution.state = state
        self.execution_repo.save(execution)
        return execution

    def mark_finished(self, session_id: int) -> None:
        execution = self.execution_repo.get_active_by_session_id(session_id)
        if execution:
            execution.status = "finished"
            state = execution.state or {}
            state["next_action"] = {
                "type": "finished",
                "reason": "interview_finished",
            }
            execution.state = state
            self.execution_repo.save(execution)

    def context_for_followup(self, execution, plan_content: dict | None = None) -> str | None:
        if not execution:
            return None

        state = execution.state or {}
        current_section = self._section_at(state, execution.current_section_index)
        next_section = self._section_at(state, execution.current_section_index + 1)
        next_action = state.get("next_action") or {}
        if not current_section and next_action.get("type") != "wrap_up_interview":
            return None

        lines = [
            "InterviewPlanExecution:",
            f"- current_section_key: {execution.current_section_key or ''}",
            f"- current_section_round_no: {execution.current_section_round_no}",
            f"- total_completed_round_no: {execution.total_completed_round_no}",
            f"- next_action: {next_action.get('type') or 'continue_current_topic'}",
            f"- next_action_reason: {next_action.get('reason') or ''}",
        ]
        if next_action.get("next_question_intent"):
            lines.append(f"- next_question_intent: {next_action.get('next_question_intent')}")

        decision_policy = state.get("decision_policy") or {}
        if decision_policy:
            lines.extend(
                [
                    f"- decision_policy_action: {decision_policy.get('final_action') or ''}",
                    f"- decision_policy_reason: {decision_policy.get('reason') or ''}",
                    f"- decision_policy_conflict_resolution: {decision_policy.get('conflict_resolution') or ''}",
                ]
            )

        last_judge = state.get("last_topic_judge") or {}
        if last_judge:
            lines.extend(
                [
                    f"- last_answer_quality: {last_judge.get('answer_quality') or ''}",
                    f"- last_topic_status: {last_judge.get('topic_status') or ''}",
                    f"- last_judge_reason: {last_judge.get('reason') or ''}",
                ]
            )

        if current_section:
            seed_question = self.first_seed_question(current_section)
            lines.extend(
                [
                    f"- current_section_title: {current_section.get('title') or ''}",
                    f"- current_section_goals: {current_section.get('goals') or []}",
                    f"- current_section_seed_question: {seed_question or ''}",
                    f"- covered_probe_points: {current_section.get('covered_probe_points') or []}",
                    f"- missing_probe_points: {current_section.get('uncovered_probe_points') or []}",
                    f"- suggested_probe_point: {self._current_probe_point(current_section)}",
                ]
            )
        if next_section:
            seed_question = self.first_seed_question(next_section)
            lines.extend(
                [
                    f"- next_section_key: {next_section.get('section_key') or ''}",
                    f"- next_section_title: {next_section.get('title') or ''}",
                    f"- next_section_seed_question: {seed_question or ''}",
                ]
            )
        if plan_content:
            lines.append(f"- total_round_target: {plan_content.get('total_round_target') or ''}")
        return "\n".join(lines)

    def response(self, execution) -> dict:
        if not execution:
            return {
                "currentSectionKey": None,
                "currentSectionRoundNo": 0,
                "totalCompletedRoundNo": 0,
                "status": "missing",
                "nextAction": None,
                "coveredProbePoints": [],
                "missingProbePoints": [],
            }

        state = execution.state or {}
        current_section = self._section_at(state, execution.current_section_index) or {}
        next_action = state.get("next_action") or {}
        return {
            "currentSectionKey": execution.current_section_key,
            "currentSectionRoundNo": execution.current_section_round_no,
            "totalCompletedRoundNo": execution.total_completed_round_no,
            "status": execution.status,
            "nextAction": next_action.get("type"),
            "coveredProbePoints": current_section.get("covered_probe_points") or [],
            "missingProbePoints": current_section.get("uncovered_probe_points") or [],
            "lastTopicJudge": state.get("last_topic_judge") or {},
            "decisionPolicy": state.get("decision_policy") or {},
            "sections": state.get("sections") or [],
        }

    def first_seed_question(self, section: dict | None) -> str | None:
        if not section:
            return None
        questions = section.get("seed_questions") or section.get("seedQuestions") or []
        return questions[0] if questions else None

    def _initial_state(self, plan_content: dict) -> dict:
        sections = []
        for index, section in enumerate(plan_content.get("sections") or []):
            probe_points = section.get("probe_points") or section.get("probePoints") or []
            sections.append(
                {
                    "section_key": section.get("section_key") or section.get("sectionKey") or f"section_{index + 1}",
                    "title": section.get("title") or "",
                    "status": "active" if index == 0 else "pending",
                    "target_rounds": int(section.get("target_rounds") or section.get("targetRounds") or 1),
                    "completed_rounds": 0,
                    "goals": section.get("goals") or [],
                    "seed_questions": section.get("seed_questions") or section.get("seedQuestions") or [],
                    "probe_points": probe_points,
                    "covered_probe_points": [],
                    "uncovered_probe_points": list(probe_points),
                    "evidence": [],
                    "completion_reason": "",
                }
            )
        return {
            "sections": sections,
            "next_action": {
                "type": "continue_current_topic",
                "reason": "interview_started",
            },
        }

    def _section_at(self, state: dict, index: int) -> dict | None:
        sections = state.get("sections") or []
        return sections[index] if 0 <= index < len(sections) else None

    def _current_probe_point(self, section: dict) -> str:
        uncovered = section.get("uncovered_probe_points") or []
        if uncovered:
            return str(uncovered[0])
        probe_points = section.get("probe_points") or []
        return str(probe_points[-1]) if probe_points else ""

    def _judge_covered_probe_points(self, section: dict, judge_result: dict | None) -> list[str]:
        covered = (judge_result or {}).get("covered_probe_points") or []
        if covered:
            return [str(item) for item in covered]
        current = self._current_probe_point(section)
        return [current] if current else []

    def _mark_probe_points_covered(self, section: dict, probe_points: list[str]) -> None:
        for probe_point in probe_points:
            self._mark_probe_point_covered(section, probe_point)

    def _mark_probe_point_covered(self, section: dict, probe_point: str) -> None:
        uncovered = section.get("uncovered_probe_points") or []
        section["uncovered_probe_points"] = [item for item in uncovered if item != probe_point]
        covered = section.get("covered_probe_points") or []
        if probe_point not in covered:
            covered.append(probe_point)
        section["covered_probe_points"] = covered

    def _move_next_section(
        self,
        *,
        execution,
        state: dict,
        sections: list[dict],
        current_section: dict,
        current_index: int,
        reason: str,
        decision_source: str,
        conflict_resolution: str | None,
    ) -> None:
        current_section["status"] = "completed"
        current_section["completion_reason"] = reason
        next_index = current_index + 1
        next_section = sections[next_index] if next_index < len(sections) else None
        if not next_section:
            self._mark_wrap_up(execution, state, "all_sections_completed")
            return

        next_section["status"] = "active"
        execution.current_section_index = next_index
        execution.current_section_key = next_section.get("section_key")
        execution.current_section_round_no = 0
        state["next_action"] = {
            "type": "move_next_section",
            "decision_source": decision_source,
            "conflict_resolution": conflict_resolution,
            "reason": reason,
        }

    def _next_action_for_policy(
        self,
        section: dict,
        judge_result: dict | None,
        policy_result,
    ) -> dict:
        next_action = policy_result.final_action
        if next_action not in {"continue_current_topic", "switch_topic_in_section"}:
            next_action = "continue_current_topic"
        return {
            "type": next_action,
            "reason": policy_result.reason,
            "next_question_intent": (judge_result or {}).get("next_question_intent", ""),
            "decision_source": policy_result.source,
            "conflict_resolution": policy_result.conflict_resolution,
        }

    def _next_action_for_section(self, section: dict, judge_result: dict | None = None) -> dict:
        policy_result = self.decision_policy.decide(
            DecisionPolicyInput(
                topic_judge_result=judge_result,
                execution_state={},
                current_section=section,
                current_section_index=0,
                section_count=1,
                completed_rounds=int(section.get("completed_rounds") or 0),
                target_rounds=int(section.get("target_rounds") or 1),
                open_threads=(judge_result or {}).get("open_threads") or [],
            )
        )
        return self._next_action_for_policy(section, judge_result, policy_result)

    def _mark_wrap_up(self, execution, state: dict, reason: str) -> None:
        execution.current_section_key = None
        execution.current_section_round_no = 0
        execution.status = "wrapping_up"
        state["next_action"] = {
            "type": "wrap_up_interview",
            "decision_source": "decision_policy",
            "reason": reason,
        }
