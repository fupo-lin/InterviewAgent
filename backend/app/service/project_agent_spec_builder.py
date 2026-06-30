from dataclasses import dataclass

from app.service.agent_run_service import AgentRunExecutor, AgentSpec
from app.service.evidence_service import EvidencePacketBuilder


@dataclass(frozen=True)
class ProjectAgentContext:
    jd_analysis: object | None = None
    resume_profile: object | None = None
    gap_analysis: object | None = None
    candidate_profile: object | None = None


class ProjectAgentSpecBuilder:
    def __init__(
        self,
        agent_run_executor: AgentRunExecutor,
        evidence_builder: EvidencePacketBuilder,
    ) -> None:
        self.agent_run_executor = agent_run_executor
        self.evidence_builder = evidence_builder

    def project_candidate_profile(
        self,
        project_id: int,
        target_role: str | None,
        source_session_id: int | None,
        execution_state: dict | None,
        evaluation: dict | None,
        transcript_messages: list | None,
        context: ProjectAgentContext,
    ) -> AgentSpec:
        evidence_packet = self.evidence_builder.build_resume_packet(
            task="project_candidate_profile",
            project_id=project_id,
            resume_profile=context.resume_profile.content if context.resume_profile else None,
            execution_state=execution_state,
            transcript_messages=transcript_messages or [],
        )
        return self.agent_run_executor.spec(
            prompt_id="project_candidate_profile",
            project_id=project_id,
            session_id=source_session_id,
            input_snapshot={
                "target_role": target_role,
                "has_jd_analysis": bool(context.jd_analysis),
                "has_resume_profile": bool(context.resume_profile),
                "has_gap_analysis": bool(context.gap_analysis),
                "has_evaluation": bool(evaluation),
                "transcript_message_count": len(transcript_messages or []),
            },
            context_refs={
                "jd_analysis_id": context.jd_analysis.id if context.jd_analysis else None,
                "resume_profile_id": context.resume_profile.id if context.resume_profile else None,
                "gap_analysis_id": context.gap_analysis.id if context.gap_analysis else None,
                "source_session_id": source_session_id,
            },
            evidence_packet=evidence_packet,
        )

    def resume_authenticity(
        self,
        project_id: int,
        resume_id: int,
        session_id: int | None,
        execution_state: dict | None,
        transcript_messages: list | None,
        context: ProjectAgentContext,
    ) -> AgentSpec:
        evidence_packet = self.evidence_builder.build_resume_packet(
            task="resume_authenticity_check",
            project_id=project_id,
            resume_profile=context.resume_profile.content if context.resume_profile else None,
            execution_state=execution_state,
            transcript_messages=transcript_messages or [],
        )
        return self.agent_run_executor.spec(
            prompt_id="resume_authenticity",
            project_id=project_id,
            session_id=session_id,
            input_snapshot={
                "resume_id": resume_id,
                "has_resume_profile": bool(context.resume_profile),
                "has_jd_analysis": bool(context.jd_analysis),
                "has_gap_analysis": bool(context.gap_analysis),
                "has_project_candidate_profile": bool(context.candidate_profile),
            },
            context_refs={
                "resume_profile_id": context.resume_profile.id if context.resume_profile else None,
                "jd_analysis_id": context.jd_analysis.id if context.jd_analysis else None,
                "gap_analysis_id": context.gap_analysis.id if context.gap_analysis else None,
                "project_candidate_profile_id": context.candidate_profile.id if context.candidate_profile else None,
            },
            evidence_packet=evidence_packet,
        )

    def resume_rewrite(
        self,
        project_id: int,
        resume_id: int,
        rewrite_mode: str,
        authenticity_report_id: int | None,
        resume_authenticity: dict | None,
        execution_state: dict | None,
        transcript_messages: list | None,
        context: ProjectAgentContext,
    ) -> AgentSpec:
        evidence_packet = self.evidence_builder.build_resume_packet(
            task="resume_rewrite",
            project_id=project_id,
            resume_profile=context.resume_profile.content if context.resume_profile else None,
            execution_state=execution_state,
            transcript_messages=transcript_messages or [],
            authenticity_report=resume_authenticity,
        )
        return self.agent_run_executor.spec(
            prompt_id="resume_rewrite",
            project_id=project_id,
            session_id=None,
            input_snapshot={
                "resume_id": resume_id,
                "rewrite_mode": rewrite_mode,
                "authenticity_report_id": authenticity_report_id,
                "has_resume_profile": bool(context.resume_profile),
                "has_jd_analysis": bool(context.jd_analysis),
                "has_gap_analysis": bool(context.gap_analysis),
                "has_project_candidate_profile": bool(context.candidate_profile),
            },
            context_refs={
                "resume_profile_id": context.resume_profile.id if context.resume_profile else None,
                "jd_analysis_id": context.jd_analysis.id if context.jd_analysis else None,
                "gap_analysis_id": context.gap_analysis.id if context.gap_analysis else None,
                "project_candidate_profile_id": context.candidate_profile.id if context.candidate_profile else None,
                "authenticity_report_id": authenticity_report_id,
            },
            evidence_packet=evidence_packet,
        )
