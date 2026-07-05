from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.service.assessment_agents import EvaluationAgent, EvaluationAgentInput
from app.service.post_interview_assessment_state import (
    AssessmentConditionCheck,
    AssessmentNextAction,
    AssessmentOutputArtifact,
    PostInterviewAssessmentState,
)


OUTPUT_CONTRACT_VERSION = "PostInterviewAssessmentOutput.v1"
MIN_USER_ANSWER_COUNT_FOR_EVALUATION = 1


@dataclass(frozen=True)
class PostInterviewAssessmentContext:
    existing_evaluation: Any | None
    history: list
    full_history: list
    execution: Any | None
    candidate_profile: Any | None
    conversation_summary: Any | None
    plan_context: str | None


class PostInterviewAssessmentNodes:
    def __init__(
        self,
        *,
        message_repo,
        evaluation_repo,
        summary_repo,
        execution_repo,
        plan_repo,
        session_repo,
        execution_service: Any,
        evaluation_agent: EvaluationAgent,
    ) -> None:
        self.message_repo = message_repo
        self.evaluation_repo = evaluation_repo
        self.summary_repo = summary_repo
        self.execution_repo = execution_repo
        self.plan_repo = plan_repo
        self.session_repo = session_repo
        self.execution_service = execution_service
        self.evaluation_agent = evaluation_agent

    def initial_state(
        self,
        session,
        incoming_trigger: str = "interview_end",
    ) -> PostInterviewAssessmentState:
        return {
            "workflow_id": "post_interview_assessment",
            "thread_id": f"assessment:{session.session_uid}",
            "status": "running",
            "active_step": None,
            "project_id": session.project_id,
            "session_id": session.id,
            "session_uid": session.session_uid,
            "incoming_trigger": incoming_trigger,
            "completed_steps": [],
            "skipped_steps": [],
            "failed_steps": [],
            "last_error": None,
            "partial_reason": None,
            "resume_reason": None,
            "resume_from_step": None,
            "branch": None,
            "branch_reason": None,
            "branch_decisions": [],
            "output_contract_version": OUTPUT_CONTRACT_VERSION,
            "outputs": {
                "contract_version": OUTPUT_CONTRACT_VERSION,
                "artifacts": [],
                "next_actions": [],
            },
            "next_actions": [],
        }

    def load_context_node(
        self,
        state: PostInterviewAssessmentState,
        session,
    ) -> PostInterviewAssessmentContext:
        existing = self.evaluation_repo.get_latest_by_session_id(session.id)
        full_history = self.message_repo.list_by_session_id(session.id)
        context = PostInterviewAssessmentContext(
            existing_evaluation=existing,
            history=self._evaluation_context(session.id),
            full_history=full_history,
            execution=self.execution_repo.get_latest_by_session_id(session.id),
            candidate_profile=self.summary_repo.get_latest_by_session_id(
                session.id,
                "candidate_profile",
            ),
            conversation_summary=self.summary_repo.get_latest_by_session_id(
                session.id,
                "conversation",
            ),
            plan_context=self._session_plan_context(session),
        )
        state["execution_id"] = context.execution.id if context.execution else None
        state["candidate_profile_summary_id"] = (
            context.candidate_profile.id if context.candidate_profile else None
        )
        state["conversation_summary_id"] = (
            context.conversation_summary.id if context.conversation_summary else None
        )
        self._complete(state, "load_assessment_context")
        return context

    async def ensure_evaluation_node(
        self,
        state: PostInterviewAssessmentState,
        session,
        context: PostInterviewAssessmentContext,
    ):
        if context.existing_evaluation:
            state["evaluation_id"] = context.existing_evaluation.id
            state["evaluation_agent_run_id"] = getattr(
                context.existing_evaluation,
                "agent_run_id",
                None,
            )
            self._record_branch_decision(
                state,
                step_id="ensure_evaluation",
                branch="reuse_existing_evaluation",
                reason="existing_evaluation_found",
                condition_checks=[
                    {
                        "name": "evaluation_exists",
                        "ok": True,
                        "value": context.existing_evaluation.id,
                        "detail": "Latest evaluation artifact was found for this session.",
                    }
                ],
            )
            self._complete(state, "evaluation")
            self._record_output_artifact(
                state,
                name="evaluation",
                artifact_kind="interview_evaluation",
                artifact_id=context.existing_evaluation.id,
                source="reused_existing_artifact",
                required=True,
                status="available",
            )
            self._complete(state, "ensure_evaluation_reused")
            return context.existing_evaluation

        user_answer_count = self._user_answer_count(context.full_history)
        if user_answer_count < MIN_USER_ANSWER_COUNT_FOR_EVALUATION:
            state["partial_reason"] = "insufficient_transcript"
            self._record_branch_decision(
                state,
                step_id="ensure_evaluation",
                branch="skip_evaluation_insufficient_transcript",
                reason="insufficient_transcript",
                condition_checks=[
                    {
                        "name": "evaluation_exists",
                        "ok": False,
                        "value": None,
                        "detail": "No reusable evaluation artifact was found for this session.",
                    },
                    {
                        "name": "has_enough_transcript",
                        "ok": False,
                        "value": user_answer_count,
                        "detail": (
                            "At least one user answer is required before generating "
                            "an interview evaluation."
                        ),
                    },
                ],
            )
            self._record_output_artifact(
                state,
                name="evaluation",
                artifact_kind="interview_evaluation",
                artifact_id=None,
                source="skipped_by_workflow",
                required=True,
                status="skipped",
                reason="insufficient_transcript",
            )
            self._skip(state, "evaluation")
            self._skip(state, "ensure_evaluation")
            return None

        self._record_branch_decision(
            state,
            step_id="ensure_evaluation",
            branch="generated_evaluation",
            reason="no_existing_evaluation",
            condition_checks=[
                {
                    "name": "evaluation_exists",
                    "ok": False,
                    "value": None,
                    "detail": "No reusable evaluation artifact was found for this session.",
                },
                {
                    "name": "has_enough_transcript",
                    "ok": True,
                    "value": user_answer_count,
                    "detail": "Transcript contains enough user answers for evaluation.",
                }
            ],
        )
        run_result = await self.evaluation_agent.run(
            EvaluationAgentInput(
                session=session,
                history=context.history,
                full_history=context.full_history,
                execution=context.execution,
                candidate_profile=context.candidate_profile,
                conversation_summary=context.conversation_summary,
                plan_context=context.plan_context,
                workflow_run_id=state.get("workflow_run_id"),
            )
        )
        saved = self.evaluation_repo.create(
            session_id=session.id,
            strengths=run_result.output["strengths"],
            weaknesses=run_result.output["weaknesses"],
            suggestions=run_result.output["suggestions"],
            summary=run_result.output.get("summary"),
            technical_ability=run_result.output.get("technical_ability"),
            project_experience=run_result.output.get("project_experience"),
            communication=run_result.output.get("communication"),
            improvement_suggestions=run_result.output.get("improvement_suggestions"),
            agent_run_id=run_result.agent_run.id,
            schema_version=run_result.output_schema,
            evidence_refs=run_result.evidence_refs,
        )
        state["evaluation_id"] = saved.id
        state["evaluation_agent_run_id"] = run_result.agent_run.id
        self._complete(state, "evaluation")
        self._record_output_artifact(
            state,
            name="evaluation",
            artifact_kind="interview_evaluation",
            artifact_id=saved.id,
            source="generated_by_workflow",
            required=True,
            status="available",
        )
        self._complete(state, "ensure_evaluation")
        return saved

    def record_project_outputs(
        self,
        state: PostInterviewAssessmentState,
        *,
        project_candidate_profile_id: int | None = None,
        resume_authenticity_report_id: int | None = None,
    ) -> None:
        if project_candidate_profile_id is not None:
            self._record_output_artifact(
                state,
                name="project_candidate_profile",
                artifact_kind="project_candidate_profile",
                artifact_id=project_candidate_profile_id,
                source="generated_after_assessment",
                required=False,
                status="available",
            )
        if resume_authenticity_report_id is not None:
            self._record_output_artifact(
                state,
                name="resume_authenticity",
                artifact_kind="resume_authenticity_report",
                artifact_id=resume_authenticity_report_id,
                source="generated_after_assessment",
                required=False,
                status="available",
            )
            self._record_next_action(
                state,
                action_type="resume_optimization_ready",
                reason="resume_authenticity_report_available",
                artifact_name="resume_authenticity",
            )

    def complete_node(
        self,
        state: PostInterviewAssessmentState,
        session,
    ) -> None:
        self.session_repo.mark_finished(session)
        self.execution_service.mark_finished(session.id)
        state["active_step"] = None
        self._complete(state, "complete")

    def _evaluation_context(self, session_id: int):
        latest_completed_round_no = self.message_repo.latest_completed_round_no(session_id)
        if latest_completed_round_no <= 15:
            return self.message_repo.list_by_session_id(session_id)
        return self.message_repo.list_recent_rounds(session_id, rounds=8)

    def _session_plan_context(self, session) -> str | None:
        if not session.interview_plan_id:
            return None
        plan = self.plan_repo.get_by_id(session.interview_plan_id)
        if not plan:
            return None
        content = plan.content or {}
        return (
            f"InterviewPlan mode: {plan.plan_mode}\n"
            f"Role: {content.get('role_name') or content.get('roleName') or ''}\n"
            f"Sections: {content.get('sections', [])}\n"
            f"Evaluation rubric: "
            f"{content.get('evaluation_rubric') or content.get('evaluationRubric') or []}"
        )

    def _complete(self, state: PostInterviewAssessmentState, step_id: str) -> None:
        completed_steps = state.setdefault("completed_steps", [])
        if step_id not in completed_steps:
            completed_steps.append(step_id)

    def _skip(self, state: PostInterviewAssessmentState, step_id: str) -> None:
        skipped_steps = state.setdefault("skipped_steps", [])
        if step_id not in skipped_steps:
            skipped_steps.append(step_id)

    def _user_answer_count(self, messages: list) -> int:
        return sum(
            1
            for item in messages or []
            if getattr(item, "role_type", None) == "user"
            and getattr(item, "status", "normal") != "deleted"
        )

    def _record_branch_decision(
        self,
        state: PostInterviewAssessmentState,
        *,
        step_id: str,
        branch: str,
        reason: str,
        condition_checks: list[AssessmentConditionCheck],
    ) -> None:
        decision = {
            "step_id": step_id,
            "branch": branch,
            "reason": reason,
            "condition_checks": condition_checks,
        }
        state["branch"] = branch
        state["branch_reason"] = reason
        decisions = state.setdefault("branch_decisions", [])
        decisions[:] = [
            item
            for item in decisions
            if item.get("step_id") != step_id
        ]
        decisions.append(decision)

    def _record_output_artifact(
        self,
        state: PostInterviewAssessmentState,
        *,
        name: str,
        artifact_kind: str,
        artifact_id: int | None,
        source: str,
        required: bool,
        status: str,
        reason: str | None = None,
    ) -> None:
        artifact: AssessmentOutputArtifact = {
            "name": name,
            "artifact_kind": artifact_kind,
            "artifact_id": artifact_id,
            "source": source,
            "required": required,
            "status": status,
            "reason": reason,
        }
        outputs = self._outputs(state)
        artifacts = outputs.setdefault("artifacts", [])
        artifacts[:] = [
            item
            for item in artifacts
            if item.get("name") != name
        ]
        artifacts.append(artifact)

    def _record_next_action(
        self,
        state: PostInterviewAssessmentState,
        *,
        action_type: str,
        reason: str,
        artifact_name: str | None = None,
    ) -> None:
        action: AssessmentNextAction = {
            "type": action_type,
            "reason": reason,
            "artifact_name": artifact_name,
        }
        actions = state.setdefault("next_actions", [])
        actions[:] = [
            item
            for item in actions
            if item.get("type") != action_type
        ]
        actions.append(action)

        outputs = self._outputs(state)
        output_actions = outputs.setdefault("next_actions", [])
        output_actions[:] = [
            item
            for item in output_actions
            if item.get("type") != action_type
        ]
        output_actions.append(action)

    def _outputs(self, state: PostInterviewAssessmentState):
        outputs = state.setdefault(
            "outputs",
            {
                "contract_version": OUTPUT_CONTRACT_VERSION,
                "artifacts": [],
                "next_actions": [],
            },
        )
        outputs["contract_version"] = OUTPUT_CONTRACT_VERSION
        state["output_contract_version"] = OUTPUT_CONTRACT_VERSION
        return outputs
