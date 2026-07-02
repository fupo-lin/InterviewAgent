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

    def jd_analysis(
        self,
        project_id: int,
        jd,
    ) -> AgentSpec:
        evidence_packet = self.evidence_builder.build_jd_analysis_packet(
            project_id=project_id,
            jd_id=jd.id,
            jd_content=jd.raw_content,
        )
        return self.agent_run_executor.spec(
            prompt_id="jd_analysis",
            project_id=project_id,
            session_id=None,
            input_snapshot={
                "jd_id": jd.id,
                "content_length": len(jd.raw_content or ""),
                "has_title": bool(jd.title),
                "has_company_name": bool(jd.company_name),
                "has_source_url": bool(jd.source_url),
            },
            context_refs={
                "jd_id": jd.id,
                "project_id": project_id,
            },
            evidence_packet=evidence_packet,
            workflow_context=self._workflow_context(
                workflow_id="preparation",
                step_id="jd_analysis",
                project_id=project_id,
            ),
        )

    def resume_analysis(
        self,
        project_id: int,
        resume,
    ) -> AgentSpec:
        evidence_packet = self.evidence_builder.build_resume_analysis_packet(
            project_id=project_id,
            resume_id=resume.id,
            resume_content=resume.raw_content,
        )
        return self.agent_run_executor.spec(
            prompt_id="resume_analysis",
            project_id=project_id,
            session_id=None,
            input_snapshot={
                "resume_id": resume.id,
                "content_length": len(resume.raw_content or ""),
                "file_name": resume.file_name,
                "file_type": resume.file_type,
            },
            context_refs={
                "resume_id": resume.id,
                "project_id": project_id,
            },
            evidence_packet=evidence_packet,
            workflow_context=self._workflow_context(
                workflow_id="preparation",
                step_id="resume_analysis",
                project_id=project_id,
            ),
        )

    def gap_analysis(
        self,
        project_id: int,
        jd_analysis,
        resume_profile,
    ) -> AgentSpec:
        evidence_packet = self.evidence_builder.build_gap_analysis_packet(
            project_id=project_id,
            jd_analysis_id=jd_analysis.id,
            resume_profile_id=resume_profile.id,
            jd_analysis=jd_analysis.content,
            resume_profile=resume_profile.content,
        )
        return self.agent_run_executor.spec(
            prompt_id="gap_analysis",
            project_id=project_id,
            session_id=None,
            input_snapshot={
                "jd_analysis_id": jd_analysis.id,
                "resume_profile_id": resume_profile.id,
                "jd_analysis_schema_version": getattr(jd_analysis, "schema_version", None),
                "resume_profile_schema_version": getattr(resume_profile, "schema_version", None),
            },
            context_refs={
                "jd_analysis_id": jd_analysis.id,
                "resume_profile_id": resume_profile.id,
                "jd_analysis_agent_run_id": getattr(jd_analysis, "agent_run_id", None),
                "resume_profile_agent_run_id": getattr(resume_profile, "agent_run_id", None),
                "jd_analysis_evidence_refs": getattr(jd_analysis, "evidence_refs", None) or [],
                "resume_profile_evidence_refs": getattr(resume_profile, "evidence_refs", None) or [],
            },
            evidence_packet=evidence_packet,
            workflow_context=self._workflow_context(
                workflow_id="preparation",
                step_id="gap_analysis",
                project_id=project_id,
            ),
        )

    def interview_plan(
        self,
        project_id: int,
        target_role: str | None,
        plan_mode: str,
        jd_analysis=None,
        resume_profile=None,
        gap_analysis=None,
    ) -> AgentSpec:
        evidence_packet = self.evidence_builder.build_interview_plan_packet(
            project_id=project_id,
            plan_mode=plan_mode,
            jd_analysis_id=jd_analysis.id if jd_analysis else None,
            resume_profile_id=resume_profile.id if resume_profile else None,
            gap_analysis_id=gap_analysis.id if gap_analysis else None,
            jd_analysis=jd_analysis.content if jd_analysis else None,
            resume_profile=resume_profile.content if resume_profile else None,
            gap_analysis=gap_analysis.content if gap_analysis else None,
        )
        return self.agent_run_executor.spec(
            prompt_id="interview_plan",
            project_id=project_id,
            session_id=None,
            input_snapshot={
                "plan_mode": plan_mode,
                "target_role": target_role,
                "has_jd_analysis": bool(jd_analysis),
                "has_resume_profile": bool(resume_profile),
                "has_gap_analysis": bool(gap_analysis),
            },
            context_refs={
                "jd_analysis_id": jd_analysis.id if jd_analysis else None,
                "resume_profile_id": resume_profile.id if resume_profile else None,
                "gap_analysis_id": gap_analysis.id if gap_analysis else None,
                "jd_analysis_agent_run_id": getattr(jd_analysis, "agent_run_id", None) if jd_analysis else None,
                "resume_profile_agent_run_id": getattr(resume_profile, "agent_run_id", None) if resume_profile else None,
                "gap_analysis_agent_run_id": getattr(gap_analysis, "agent_run_id", None) if gap_analysis else None,
                "jd_analysis_evidence_refs": getattr(jd_analysis, "evidence_refs", None) or [],
                "resume_profile_evidence_refs": getattr(resume_profile, "evidence_refs", None) or [],
                "gap_analysis_evidence_refs": getattr(gap_analysis, "evidence_refs", None) or [],
            },
            evidence_packet=evidence_packet,
            workflow_context=self._workflow_context(
                workflow_id="preparation",
                step_id="interview_plan",
                project_id=project_id,
            ),
        )

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
            workflow_context=self._workflow_context(
                workflow_id="post_interview_assessment",
                step_id="project_candidate_profile",
                project_id=project_id,
                session_id=source_session_id,
            ),
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
            workflow_context=self._workflow_context(
                workflow_id="resume_optimization",
                step_id="resume_authenticity",
                project_id=project_id,
                session_id=session_id,
            ),
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
            workflow_context=self._workflow_context(
                workflow_id="resume_optimization",
                step_id="resume_rewrite",
                project_id=project_id,
            ),
        )

    def _workflow_context(
        self,
        workflow_id: str,
        step_id: str,
        project_id: int | None = None,
        session_id: int | None = None,
    ) -> dict:
        return {
            "workflow_id": workflow_id,
            "workflow_run_id": self._workflow_run_id(
                workflow_id=workflow_id,
                project_id=project_id,
                session_id=session_id,
            ),
            "step_id": step_id,
        }

    def _workflow_run_id(
        self,
        workflow_id: str,
        project_id: int | None = None,
        session_id: int | None = None,
    ) -> str:
        if session_id is not None:
            return f"session_{session_id}_{workflow_id}"
        if project_id is not None:
            return f"project_{project_id}_{workflow_id}"
        return workflow_id
