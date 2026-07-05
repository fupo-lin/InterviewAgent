from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from app.service.assessment_agents import (
    GrowthReportAgent,
    GrowthReportAgentInput,
    GrowthReportContext,
)
from app.service.candidate_growth_report_state import (
    CandidateGrowthReportState,
    GrowthReportConditionCheck,
    GrowthReportOutputArtifact,
)


REPORT_VERSION = "v1"
OUTPUT_CONTRACT_VERSION = "CandidateGrowthReportOutput.v1"
MIN_USER_ANSWER_COUNT_FOR_GROWTH_REPORT = 1


@dataclass(frozen=True)
class CandidateGrowthReportContext:
    existing_report: Any | None
    messages: list
    execution: Any | None
    evaluation: Any | None
    jd_analysis: Any | None
    resume_profile: Any | None
    gap_analysis: Any | None
    project_candidate_profile: Any | None
    resume_authenticity: Any | None
    evidence_packet: dict | None = None
    generated_content: dict | None = None
    generated_raw_response: dict | None = None
    generated_evidence_refs: list[str] | None = None


class CandidateGrowthReportNodes:
    def __init__(
        self,
        *,
        message_repo,
        execution_repo,
        evaluation_repo,
        growth_report_repo,
        jd_analysis_repo,
        resume_profile_repo,
        gap_analysis_repo,
        project_candidate_profile_repo,
        resume_authenticity_repo,
        evidence_builder,
        growth_report_agent: GrowthReportAgent,
    ) -> None:
        self.message_repo = message_repo
        self.execution_repo = execution_repo
        self.evaluation_repo = evaluation_repo
        self.growth_report_repo = growth_report_repo
        self.jd_analysis_repo = jd_analysis_repo
        self.resume_profile_repo = resume_profile_repo
        self.gap_analysis_repo = gap_analysis_repo
        self.project_candidate_profile_repo = project_candidate_profile_repo
        self.resume_authenticity_repo = resume_authenticity_repo
        self.evidence_builder = evidence_builder
        self.growth_report_agent = growth_report_agent

    def initial_state(
        self,
        session,
        incoming_trigger: str = "manual_generate",
    ) -> CandidateGrowthReportState:
        return {
            "workflow_id": "candidate_growth_report",
            "thread_id": f"growth:{session.session_uid}",
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
            "missing_inputs": [],
            "resume_reason": None,
            "resume_from_step": None,
            "branch": None,
            "branch_reason": None,
            "branch_decisions": [],
            "outputs": {
                "contract_version": OUTPUT_CONTRACT_VERSION,
                "artifacts": [],
                "next_actions": [],
            },
            "next_actions": [],
        }

    def load_context_node(
        self,
        state: CandidateGrowthReportState,
        session,
    ) -> CandidateGrowthReportContext:
        existing = self.growth_report_repo.get_latest_by_session_id(
            session.id,
            report_version=REPORT_VERSION,
        )
        messages = self.message_repo.list_by_session_id(session.id)
        execution = self.execution_repo.get_latest_by_session_id(session.id)
        evaluation = self.evaluation_repo.get_latest_by_session_id(session.id)
        jd_analysis = None
        resume_profile = None
        gap_analysis = None
        project_candidate_profile = None
        resume_authenticity = None
        if session.project_id:
            jd_analysis = self.jd_analysis_repo.get_latest_by_project_id(session.project_id)
            resume_profile = self.resume_profile_repo.get_latest_by_project_id(session.project_id)
            gap_analysis = self.gap_analysis_repo.get_latest_by_project_id(session.project_id)
            project_candidate_profile = (
                self.project_candidate_profile_repo.get_latest_by_project_id(session.project_id)
            )
            resume_authenticity = self.resume_authenticity_repo.get_latest_by_project_id(
                session.project_id
            )

        state["evaluation_id"] = evaluation.id if evaluation else None
        state["execution_id"] = execution.id if execution else None
        state["jd_analysis_id"] = jd_analysis.id if jd_analysis else None
        state["resume_profile_id"] = resume_profile.id if resume_profile else None
        state["gap_analysis_id"] = gap_analysis.id if gap_analysis else None
        state["project_candidate_profile_id"] = (
            project_candidate_profile.id if project_candidate_profile else None
        )
        state["resume_authenticity_report_id"] = (
            resume_authenticity.id if resume_authenticity else None
        )
        if existing:
            state["growth_report_id"] = existing.id
            state["growth_report_uid"] = existing.report_uid
            state["growth_agent_run_id"] = existing.agent_run_id
        self._complete(state, "load_growth_context")
        return CandidateGrowthReportContext(
            existing_report=existing,
            messages=messages,
            execution=execution,
            evaluation=evaluation,
            jd_analysis=jd_analysis,
            resume_profile=resume_profile,
            gap_analysis=gap_analysis,
            project_candidate_profile=project_candidate_profile,
            resume_authenticity=resume_authenticity,
        )

    def build_evidence_node(
        self,
        state: CandidateGrowthReportState,
        session,
        context: CandidateGrowthReportContext,
    ) -> CandidateGrowthReportContext:
        packet = self.evidence_builder.build_growth_report_packet(
            session_id=session.id,
            project_id=session.project_id,
            transcript_messages=context.messages,
            execution_state=context.execution.state if context.execution else None,
            evaluation_id=context.evaluation.id if context.evaluation else None,
            evaluation=self._evaluation_payload(context.evaluation),
            jd_analysis_id=context.jd_analysis.id if context.jd_analysis else None,
            jd_analysis=context.jd_analysis.content if context.jd_analysis else None,
            resume_profile_id=context.resume_profile.id if context.resume_profile else None,
            resume_profile=context.resume_profile.content if context.resume_profile else None,
            gap_analysis_id=context.gap_analysis.id if context.gap_analysis else None,
            gap_analysis=context.gap_analysis.content if context.gap_analysis else None,
            authenticity_report=(
                context.resume_authenticity.content if context.resume_authenticity else None
            ),
        )
        state["evidence_packet_id"] = packet.get("packet_id")
        self._complete(state, "build_growth_evidence")
        return self._replace_context(context, evidence_packet=packet)

    def ensure_report_node(
        self,
        state: CandidateGrowthReportState,
        context: CandidateGrowthReportContext,
    ) -> CandidateGrowthReportContext:
        if context.existing_report:
            self._record_branch_decision(
                state,
                step_id="ensure_growth_report",
                branch="reuse_existing_growth_report",
                reason="existing_growth_report_found",
                condition_checks=[
                    {
                        "name": "growth_report_exists",
                        "ok": True,
                        "value": context.existing_report.id,
                        "detail": "Latest growth report artifact was found for this session.",
                    }
                ],
            )
            self._record_output_artifact(
                state,
                name="candidate_growth_report",
                artifact_kind="candidate_growth_report",
                artifact_id=context.existing_report.id,
                source="reused_existing_artifact",
                required=True,
                status="available",
            )
            self._complete(state, "ensure_growth_report_reused")
            return context

        user_answer_count = self._user_answer_count(context.messages)
        missing_inputs = []
        if user_answer_count < MIN_USER_ANSWER_COUNT_FOR_GROWTH_REPORT:
            missing_inputs.append("interview_answer")
        if not context.evaluation:
            missing_inputs.append("evaluation")

        if missing_inputs:
            state["partial_reason"] = "missing_required_growth_report_inputs"
            state["missing_inputs"] = missing_inputs
            self._record_branch_decision(
                state,
                step_id="ensure_growth_report",
                branch="skip_growth_report_missing_inputs",
                reason="missing_required_inputs",
                condition_checks=[
                    {
                        "name": "has_enough_transcript",
                        "ok": "interview_answer" not in missing_inputs,
                        "value": user_answer_count,
                        "detail": "At least one user answer is required.",
                    },
                    {
                        "name": "has_evaluation",
                        "ok": "evaluation" not in missing_inputs,
                        "value": context.evaluation.id if context.evaluation else None,
                        "detail": "An interview evaluation is required.",
                    },
                ],
            )
            self._record_output_artifact(
                state,
                name="candidate_growth_report",
                artifact_kind="candidate_growth_report",
                artifact_id=None,
                source="skipped_by_workflow",
                required=True,
                status="skipped",
                reason="missing_required_inputs",
            )
            self._skip(state, "generate_growth_report")
            self._skip(state, "persist_growth_report")
            self._complete(state, "ensure_growth_report")
            return context

        self._record_branch_decision(
            state,
            step_id="ensure_growth_report",
            branch="generate_new_growth_report",
            reason="no_existing_growth_report",
            condition_checks=[
                {
                    "name": "growth_report_exists",
                    "ok": False,
                    "value": None,
                    "detail": "No reusable growth report artifact was found for this session.",
                },
                {
                    "name": "has_required_inputs",
                    "ok": True,
                    "value": user_answer_count,
                    "detail": "Transcript and evaluation are available.",
                },
            ],
        )
        self._complete(state, "ensure_growth_report")
        return context

    async def generate_report_node(
        self,
        state: CandidateGrowthReportState,
        session,
        context: CandidateGrowthReportContext,
    ) -> CandidateGrowthReportContext:
        if context.existing_report or state.get("partial_reason"):
            return context
        run_result = await self.growth_report_agent.run(
            GrowthReportAgentInput(
                session=session,
                transcript_messages=context.messages,
                execution=context.execution,
                evaluation=context.evaluation,
                context=GrowthReportContext(
                    jd_analysis=context.jd_analysis,
                    resume_profile=context.resume_profile,
                    gap_analysis=context.gap_analysis,
                    project_candidate_profile=context.project_candidate_profile,
                    resume_authenticity=context.resume_authenticity,
                ),
                workflow_run_id=state.get("workflow_run_id"),
            )
        )
        state["growth_agent_run_id"] = run_result.agent_run.id
        self._complete(state, "generate_growth_report")
        return self._replace_context(
            context,
            generated_content=run_result.output,
            generated_raw_response=run_result.raw_response,
            generated_evidence_refs=run_result.evidence_refs,
        )

    def persist_report_node(
        self,
        state: CandidateGrowthReportState,
        session,
        context: CandidateGrowthReportContext,
    ) -> Any | None:
        if context.existing_report:
            return context.existing_report
        if state.get("partial_reason"):
            return None
        existing = self.growth_report_repo.get_latest_by_session_id(
            session.id,
            report_version=REPORT_VERSION,
        )
        if existing:
            state["growth_report_id"] = existing.id
            state["growth_report_uid"] = existing.report_uid
            state["growth_agent_run_id"] = existing.agent_run_id
            self._record_output_artifact(
                state,
                name="candidate_growth_report",
                artifact_kind="candidate_growth_report",
                artifact_id=existing.id,
                source="reused_existing_artifact",
                required=True,
                status="available",
            )
            self._complete(state, "persist_growth_report_reused")
            return existing

        saved = self.growth_report_repo.create(
            report_uid=uuid4().hex,
            project_id=session.project_id,
            session_id=session.id,
            workflow_run_id=state.get("workflow_run_id"),
            content=context.generated_content or {},
            raw_response=context.generated_raw_response,
            agent_run_id=state.get("growth_agent_run_id"),
            schema_version="CandidateGrowthReport.v1",
            report_version=REPORT_VERSION,
            source_snapshot=self._source_snapshot(session, context),
            evidence_refs=context.generated_evidence_refs or [],
        )
        state["growth_report_id"] = saved.id
        state["growth_report_uid"] = saved.report_uid
        self._record_output_artifact(
            state,
            name="candidate_growth_report",
            artifact_kind="candidate_growth_report",
            artifact_id=saved.id,
            source="generated_by_workflow",
            required=True,
            status="available",
        )
        self._complete(state, "persist_growth_report")
        return saved

    def complete_node(self, state: CandidateGrowthReportState) -> None:
        state["active_step"] = None
        if state.get("growth_report_id"):
            self._record_next_action(state, action_type="view_report", reason="growth_report_available")
        else:
            self._record_next_action(
                state,
                action_type="collect_required_inputs",
                reason=state.get("partial_reason") or "growth_report_unavailable",
            )
        self._complete(state, "complete")

    def _evaluation_payload(self, evaluation) -> dict | None:
        if not evaluation:
            return None
        return {
            "strengths": evaluation.strengths,
            "weaknesses": evaluation.weaknesses,
            "suggestions": evaluation.suggestions,
            "technical_ability": evaluation.technical_ability,
            "project_experience": evaluation.project_experience,
            "communication": evaluation.communication,
            "improvement_suggestions": evaluation.improvement_suggestions,
            "summary": evaluation.summary,
        }

    def _source_snapshot(self, session, context: CandidateGrowthReportContext) -> dict:
        return {
            "session_uid": session.session_uid,
            "evaluation_id": context.evaluation.id if context.evaluation else None,
            "execution_id": context.execution.id if context.execution else None,
            "jd_analysis_id": context.jd_analysis.id if context.jd_analysis else None,
            "resume_profile_id": context.resume_profile.id if context.resume_profile else None,
            "gap_analysis_id": context.gap_analysis.id if context.gap_analysis else None,
            "project_candidate_profile_id": (
                context.project_candidate_profile.id if context.project_candidate_profile else None
            ),
            "resume_authenticity_report_id": (
                context.resume_authenticity.id if context.resume_authenticity else None
            ),
            "message_count": len(context.messages or []),
            "report_version": REPORT_VERSION,
        }

    def _user_answer_count(self, messages: list) -> int:
        return sum(
            1
            for item in messages or []
            if getattr(item, "role_type", None) == "user"
            and getattr(item, "status", "normal") != "deleted"
        )

    def _complete(self, state: CandidateGrowthReportState, step_id: str) -> None:
        completed_steps = state.setdefault("completed_steps", [])
        if step_id not in completed_steps:
            completed_steps.append(step_id)

    def _skip(self, state: CandidateGrowthReportState, step_id: str) -> None:
        skipped_steps = state.setdefault("skipped_steps", [])
        if step_id not in skipped_steps:
            skipped_steps.append(step_id)

    def _record_branch_decision(
        self,
        state: CandidateGrowthReportState,
        *,
        step_id: str,
        branch: str,
        reason: str,
        condition_checks: list[GrowthReportConditionCheck],
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
        decisions[:] = [item for item in decisions if item.get("step_id") != step_id]
        decisions.append(decision)

    def _record_output_artifact(
        self,
        state: CandidateGrowthReportState,
        *,
        name: str,
        artifact_kind: str,
        artifact_id: int | None,
        source: str,
        required: bool,
        status: str,
        reason: str | None = None,
    ) -> None:
        artifact: GrowthReportOutputArtifact = {
            "name": name,
            "artifact_kind": artifact_kind,
            "artifact_id": artifact_id,
            "source": source,
            "required": required,
            "status": status,
            "reason": reason,
        }
        outputs = state.setdefault(
            "outputs",
            {
                "contract_version": OUTPUT_CONTRACT_VERSION,
                "artifacts": [],
                "next_actions": [],
            },
        )
        artifacts = outputs.setdefault("artifacts", [])
        artifacts[:] = [item for item in artifacts if item.get("name") != name]
        artifacts.append(artifact)

    def _record_next_action(
        self,
        state: CandidateGrowthReportState,
        *,
        action_type: str,
        reason: str,
    ) -> None:
        action = {"type": action_type, "reason": reason}
        actions = state.setdefault("next_actions", [])
        actions[:] = [item for item in actions if item.get("type") != action_type]
        actions.append(action)
        outputs = state.setdefault(
            "outputs",
            {
                "contract_version": OUTPUT_CONTRACT_VERSION,
                "artifacts": [],
                "next_actions": [],
            },
        )
        output_actions = outputs.setdefault("next_actions", [])
        output_actions[:] = [
            item for item in output_actions if item.get("type") != action_type
        ]
        output_actions.append(action)

    def _replace_context(self, context: CandidateGrowthReportContext, **updates):
        values = {
            "existing_report": context.existing_report,
            "messages": context.messages,
            "execution": context.execution,
            "evaluation": context.evaluation,
            "jd_analysis": context.jd_analysis,
            "resume_profile": context.resume_profile,
            "gap_analysis": context.gap_analysis,
            "project_candidate_profile": context.project_candidate_profile,
            "resume_authenticity": context.resume_authenticity,
            "evidence_packet": context.evidence_packet,
            "generated_content": context.generated_content,
            "generated_raw_response": context.generated_raw_response,
            "generated_evidence_refs": context.generated_evidence_refs,
        }
        values.update(updates)
        return CandidateGrowthReportContext(**values)
