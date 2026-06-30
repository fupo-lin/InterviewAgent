from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.repository.preparation_repository import (
    GapAnalysisRepository,
    InterviewPlanRepository,
    JDAnalysisRepository,
    JobDescriptionRepository,
    PreparationProjectRepository,
    ProjectCandidateProfileRepository,
    ResumeAuthenticityReportRepository,
    ResumeDocumentRepository,
    ResumeProfileRepository,
    ResumeRewriteResultRepository,
)
from app.repository.interview_repository import (
    InterviewEvaluationRepository,
    InterviewMessageRepository,
    InterviewPlanExecutionRepository,
    InterviewSessionRepository,
)
from app.schemas.preparation import (
    AnalysisResponse,
    GapAnalysisResponse,
    InterviewPlanResponse,
    JobDescriptionResponse,
    ProjectCandidateProfileResponse,
    ProjectOverviewResponse,
    ProjectResponse,
    ResumeAuthenticityResponse,
    ResumeDocumentResponse,
    ResumeProfileResponse,
    ResumeRewriteResponse,
)
from app.service.agent_run_service import AgentRunRecorder
from app.service.evidence_service import EvidencePacketBuilder
from app.service.llm_service import LLMService
from app.service.prompt_registry import prompt_registry


class PreparationService:
    def __init__(self, db: Session):
        self.db = db
        self.project_repo = PreparationProjectRepository(db)
        self.jd_repo = JobDescriptionRepository(db)
        self.jd_analysis_repo = JDAnalysisRepository(db)
        self.resume_repo = ResumeDocumentRepository(db)
        self.resume_profile_repo = ResumeProfileRepository(db)
        self.gap_repo = GapAnalysisRepository(db)
        self.plan_repo = InterviewPlanRepository(db)
        self.candidate_profile_repo = ProjectCandidateProfileRepository(db)
        self.authenticity_repo = ResumeAuthenticityReportRepository(db)
        self.rewrite_repo = ResumeRewriteResultRepository(db)
        self.interview_session_repo = InterviewSessionRepository(db)
        self.interview_message_repo = InterviewMessageRepository(db)
        self.interview_evaluation_repo = InterviewEvaluationRepository(db)
        self.interview_execution_repo = InterviewPlanExecutionRepository(db)
        self.llm = LLMService()
        self.evidence_builder = EvidencePacketBuilder()
        self.agent_run_recorder = AgentRunRecorder(db)

    def create_project(self, title: str, target_role: str | None = None) -> ProjectResponse:
        project = self.project_repo.create(
            project_uid=uuid4().hex,
            title=title,
            target_role=target_role,
        )
        self.db.commit()
        return self._project_response(project)

    def add_jd(
        self,
        project_uid: str,
        content: str,
        title: str | None = None,
        company_name: str | None = None,
        source_url: str | None = None,
    ) -> JobDescriptionResponse:
        project = self._get_project(project_uid)
        jd = self.jd_repo.create(
            project_id=project.id,
            raw_content=content,
            title=title,
            company_name=company_name,
            source_url=source_url,
        )
        self.db.commit()
        return JobDescriptionResponse(
            jdId=jd.id,
            title=jd.title,
            companyName=jd.company_name,
            sourceUrl=jd.source_url,
            status=jd.status,
        )

    async def analyze_jd(self, project_uid: str) -> AnalysisResponse:
        project = self._get_project(project_uid)
        jd = self.jd_repo.get_latest_by_project_id(project.id)
        if not jd:
            raise HTTPException(status_code=400, detail="Job description is required before analysis")

        evidence_packet = self.evidence_builder.build_jd_analysis_packet(
            project_id=project.id,
            jd_id=jd.id,
            jd_content=jd.raw_content,
        )
        definition = prompt_registry.get("jd_analysis")
        input_snapshot = {
            "jd_id": jd.id,
            "content_length": len(jd.raw_content or ""),
            "has_title": bool(jd.title),
            "has_company_name": bool(jd.company_name),
            "has_source_url": bool(jd.source_url),
            "evidence_packet": evidence_packet,
        }
        context_refs = {
            "jd_id": jd.id,
            "project_id": project.id,
        }
        evidence_refs = self.evidence_builder.refs(evidence_packet)
        try:
            content, raw_response = await self.llm.generate_jd_analysis(jd.raw_content)
        except Exception as exc:
            self.agent_run_recorder.record_failure(
                definition=definition,
                project_id=project.id,
                session_id=None,
                input_snapshot=input_snapshot,
                context_refs=context_refs,
                evidence_refs=evidence_refs,
                error=exc,
                model_name=self.llm.model,
            )
            self.db.commit()
            raise

        agent_run = self.agent_run_recorder.record_success(
            definition=definition,
            project_id=project.id,
            session_id=None,
            input_snapshot=input_snapshot,
            context_refs=context_refs,
            evidence_refs=evidence_refs,
            output_snapshot=content,
            raw_response=raw_response,
            model_name=self.llm.model,
        )
        saved = self.jd_analysis_repo.create(
            project_id=project.id,
            jd_id=jd.id,
            content=content,
            raw_response=raw_response,
            agent_run_id=agent_run.id,
            schema_version=definition.output_schema,
            evidence_refs=evidence_refs,
        )
        self.db.commit()
        return AnalysisResponse(analysisId=saved.id, analysis=saved.content)

    def add_resume(
        self,
        project_uid: str,
        content: str,
        file_name: str | None = None,
        file_type: str | None = None,
    ) -> ResumeDocumentResponse:
        project = self._get_project(project_uid)
        resume = self.resume_repo.create(
            project_id=project.id,
            raw_content=content,
            file_name=file_name,
            file_type=file_type,
        )
        self.db.commit()
        return ResumeDocumentResponse(
            resumeId=resume.id,
            fileName=resume.file_name,
            fileType=resume.file_type,
            status=resume.status,
        )

    async def analyze_resume(self, project_uid: str) -> ResumeProfileResponse:
        project = self._get_project(project_uid)
        resume = self.resume_repo.get_latest_by_project_id(project.id)
        if not resume:
            raise HTTPException(status_code=400, detail="Resume is required before analysis")

        evidence_packet = self.evidence_builder.build_resume_analysis_packet(
            project_id=project.id,
            resume_id=resume.id,
            resume_content=resume.raw_content,
        )
        definition = prompt_registry.get("resume_analysis")
        input_snapshot = {
            "resume_id": resume.id,
            "content_length": len(resume.raw_content or ""),
            "file_name": resume.file_name,
            "file_type": resume.file_type,
            "evidence_packet": evidence_packet,
        }
        context_refs = {
            "resume_id": resume.id,
            "project_id": project.id,
        }
        evidence_refs = self.evidence_builder.refs(evidence_packet)
        try:
            content, raw_response = await self.llm.generate_resume_profile(resume.raw_content)
        except Exception as exc:
            self.agent_run_recorder.record_failure(
                definition=definition,
                project_id=project.id,
                session_id=None,
                input_snapshot=input_snapshot,
                context_refs=context_refs,
                evidence_refs=evidence_refs,
                error=exc,
                model_name=self.llm.model,
            )
            self.db.commit()
            raise

        agent_run = self.agent_run_recorder.record_success(
            definition=definition,
            project_id=project.id,
            session_id=None,
            input_snapshot=input_snapshot,
            context_refs=context_refs,
            evidence_refs=evidence_refs,
            output_snapshot=content,
            raw_response=raw_response,
            model_name=self.llm.model,
        )
        saved = self.resume_profile_repo.create(
            project_id=project.id,
            resume_id=resume.id,
            content=content,
            raw_response=raw_response,
            agent_run_id=agent_run.id,
            schema_version=definition.output_schema,
            evidence_refs=evidence_refs,
        )
        self.db.commit()
        return ResumeProfileResponse(profileId=saved.id, profile=saved.content)

    async def analyze_gap(self, project_uid: str) -> GapAnalysisResponse:
        project = self._get_project(project_uid)
        jd_analysis = self.jd_analysis_repo.get_latest_by_project_id(project.id)
        resume_profile = self.resume_profile_repo.get_latest_by_project_id(project.id)
        if not jd_analysis or not resume_profile:
            raise HTTPException(
                status_code=400,
                detail="Gap analysis requires both JD analysis and resume profile",
            )

        content, raw_response = await self.llm.generate_gap_analysis(
            jd_analysis.content,
            resume_profile.content,
        )
        saved = self.gap_repo.create(
            project_id=project.id,
            jd_analysis_id=jd_analysis.id,
            resume_profile_id=resume_profile.id,
            content=content,
            raw_response=raw_response,
        )
        self.db.commit()
        return GapAnalysisResponse(gapAnalysisId=saved.id, gapAnalysis=saved.content)

    async def generate_interview_plan(self, project_uid: str) -> InterviewPlanResponse:
        project = self._get_project(project_uid)
        jd_analysis = self.jd_analysis_repo.get_latest_by_project_id(project.id)
        resume_profile = self.resume_profile_repo.get_latest_by_project_id(project.id)

        if not jd_analysis and not resume_profile:
            raise HTTPException(
                status_code=400,
                detail="At least JD analysis or resume profile is required before generating interview plan",
            )

        gap_analysis = None
        if jd_analysis and resume_profile:
            gap_analysis = self.gap_repo.get_latest_by_project_id(project.id)
            if not gap_analysis:
                gap_content, gap_raw = await self.llm.generate_gap_analysis(
                    jd_analysis.content,
                    resume_profile.content,
                )
                gap_analysis = self.gap_repo.create(
                    project_id=project.id,
                    jd_analysis_id=jd_analysis.id,
                    resume_profile_id=resume_profile.id,
                    content=gap_content,
                    raw_response=gap_raw,
                )

        plan_mode = self._plan_mode(jd_analysis, resume_profile)
        plan_content, raw_response = await self.llm.generate_interview_plan(
            plan_mode=plan_mode,
            jd_analysis=jd_analysis.content if jd_analysis else None,
            resume_profile=resume_profile.content if resume_profile else None,
            gap_analysis=gap_analysis.content if gap_analysis else None,
            target_role=project.target_role,
        )
        saved = self.plan_repo.create(
            project_id=project.id,
            jd_analysis_id=jd_analysis.id if jd_analysis else None,
            resume_profile_id=resume_profile.id if resume_profile else None,
            gap_analysis_id=gap_analysis.id if gap_analysis else None,
            plan_mode=plan_mode,
            content=plan_content,
            raw_response=raw_response,
        )
        self.db.commit()
        return InterviewPlanResponse(
            interviewPlanId=saved.id,
            planMode=saved.plan_mode,
            plan=saved.content,
        )

    def overview(self, project_uid: str) -> ProjectOverviewResponse:
        project = self._get_project(project_uid)
        jd = self.jd_repo.get_latest_by_project_id(project.id)
        jd_analysis = self.jd_analysis_repo.get_latest_by_project_id(project.id)
        resume = self.resume_repo.get_latest_by_project_id(project.id)
        resume_profile = self.resume_profile_repo.get_latest_by_project_id(project.id)
        gap_analysis = self.gap_repo.get_latest_by_project_id(project.id)
        interview_plan = self.plan_repo.get_latest_by_project_id(project.id)
        candidate_profile = self.candidate_profile_repo.get_latest_by_project_id(project.id)
        authenticity_report = self.authenticity_repo.get_latest_by_project_id(project.id)
        rewrite_result = self.rewrite_repo.get_latest_by_project_id(project.id)
        return ProjectOverviewResponse(
            project={
                "projectId": project.project_uid,
                "title": project.title,
                "targetRole": project.target_role,
                "status": project.status,
            },
            jd=self._jd_dict(jd) if jd else None,
            jdAnalysis=jd_analysis.content if jd_analysis else None,
            resume=self._resume_dict(resume) if resume else None,
            resumeProfile=resume_profile.content if resume_profile else None,
            gapAnalysis=gap_analysis.content if gap_analysis else None,
            interviewPlan=interview_plan.content if interview_plan else None,
            candidateProfile=candidate_profile.content if candidate_profile else None,
            resumeAuthenticity=authenticity_report.content if authenticity_report else None,
            resumeRewrite=rewrite_result.content if rewrite_result else None,
        )

    async def generate_candidate_profile(self, project_uid: str) -> ProjectCandidateProfileResponse:
        project = self._get_project(project_uid)
        session, execution, evaluation, messages = self._latest_interview_context(project.id)
        saved = await self.generate_candidate_profile_for_project(
            project.id,
            project.target_role,
            source_session_id=session.id if session else None,
            execution_state=execution.state if execution else None,
            evaluation=self._evaluation_dict(evaluation) if evaluation else None,
            transcript_messages=messages,
        )
        self.db.commit()
        return ProjectCandidateProfileResponse(profileId=saved.id, profile=saved.content)

    async def generate_resume_authenticity(self, project_uid: str) -> ResumeAuthenticityResponse:
        project = self._get_project(project_uid)
        resume = self.resume_repo.get_latest_by_project_id(project.id)
        if not resume:
            raise HTTPException(status_code=400, detail="Resume is required before authenticity analysis")

        session, execution, evaluation, messages = self._latest_interview_context(project.id)
        saved = await self.generate_resume_authenticity_for_project(
            project_id=project.id,
            resume_id=resume.id,
            resume_content=resume.raw_content,
            session_id=session.id if session else None,
            execution_state=execution.state if execution else None,
            evaluation=self._evaluation_dict(evaluation) if evaluation else None,
            transcript_messages=messages,
        )
        self.db.commit()
        return ResumeAuthenticityResponse(reportId=saved.id, report=saved.content)

    async def rewrite_resume(self, project_uid: str, rewrite_mode: str = "jd_targeted") -> ResumeRewriteResponse:
        project = self._get_project(project_uid)
        resume = self.resume_repo.get_latest_by_project_id(project.id)
        if not resume:
            raise HTTPException(status_code=400, detail="Resume is required before rewrite")

        session, execution, evaluation, messages = self._latest_interview_context(project.id)
        authenticity_report = self.authenticity_repo.get_latest_by_project_id(project.id)
        if not authenticity_report:
            authenticity_report = await self.generate_resume_authenticity_for_project(
                project_id=project.id,
                resume_id=resume.id,
                resume_content=resume.raw_content,
                session_id=session.id if session else None,
                execution_state=execution.state if execution else None,
                evaluation=self._evaluation_dict(evaluation) if evaluation else None,
                transcript_messages=messages,
            )

        saved = await self.rewrite_resume_for_project(
            project_id=project.id,
            resume_id=resume.id,
            resume_content=resume.raw_content,
            rewrite_mode=rewrite_mode,
            authenticity_report_id=authenticity_report.id if authenticity_report else None,
            resume_authenticity=authenticity_report.content if authenticity_report else None,
            execution_state=execution.state if execution else None,
            evaluation=self._evaluation_dict(evaluation) if evaluation else None,
            transcript_messages=messages,
        )
        self.db.commit()
        return ResumeRewriteResponse(
            rewriteId=saved.id,
            rewriteMode=saved.rewrite_mode,
            result=saved.content,
        )

    async def generate_candidate_profile_for_project(
        self,
        project_id: int,
        target_role: str | None = None,
        source_session_id: int | None = None,
        execution_state: dict | None = None,
        evaluation: dict | None = None,
        transcript_messages: list | None = None,
    ):
        jd_analysis = self.jd_analysis_repo.get_latest_by_project_id(project_id)
        resume_profile = self.resume_profile_repo.get_latest_by_project_id(project_id)
        gap_analysis = self.gap_repo.get_latest_by_project_id(project_id)
        evidence_packet = self.evidence_builder.build_resume_packet(
            task="project_candidate_profile",
            project_id=project_id,
            resume_profile=resume_profile.content if resume_profile else None,
            execution_state=execution_state,
            transcript_messages=transcript_messages or [],
        )
        definition = prompt_registry.get("project_candidate_profile")
        input_snapshot = {
            "target_role": target_role,
            "has_jd_analysis": bool(jd_analysis),
            "has_resume_profile": bool(resume_profile),
            "has_gap_analysis": bool(gap_analysis),
            "has_evaluation": bool(evaluation),
            "transcript_message_count": len(transcript_messages or []),
            "evidence_packet": evidence_packet,
        }
        context_refs = {
            "jd_analysis_id": jd_analysis.id if jd_analysis else None,
            "resume_profile_id": resume_profile.id if resume_profile else None,
            "gap_analysis_id": gap_analysis.id if gap_analysis else None,
            "source_session_id": source_session_id,
        }
        try:
            content, raw_response = await self.llm.generate_project_candidate_profile(
                target_role=target_role,
                jd_analysis=jd_analysis.content if jd_analysis else None,
                resume_profile=resume_profile.content if resume_profile else None,
                gap_analysis=gap_analysis.content if gap_analysis else None,
                execution_state=execution_state,
                evaluation=evaluation,
                transcript_messages=transcript_messages or [],
                evidence_packet=evidence_packet,
            )
        except Exception as exc:
            self.agent_run_recorder.record_failure(
                definition=definition,
                project_id=project_id,
                session_id=source_session_id,
                input_snapshot=input_snapshot,
                context_refs=context_refs,
                evidence_refs=self.evidence_builder.refs(evidence_packet),
                error=exc,
                model_name=self.llm.model,
            )
            self.db.commit()
            raise

        agent_run = self.agent_run_recorder.record_success(
            definition=definition,
            project_id=project_id,
            session_id=source_session_id,
            input_snapshot=input_snapshot,
            context_refs=context_refs,
            evidence_refs=self.evidence_builder.refs(evidence_packet),
            output_snapshot=content,
            raw_response=raw_response,
            model_name=self.llm.model,
        )
        return self.candidate_profile_repo.create(
            project_id=project_id,
            source_session_id=source_session_id,
            content=content,
            raw_response=raw_response,
            agent_run_id=agent_run.id,
            schema_version=definition.output_schema,
            evidence_refs=self.evidence_builder.refs(evidence_packet),
        )

    async def generate_resume_authenticity_for_project(
        self,
        project_id: int,
        resume_id: int,
        resume_content: str,
        session_id: int | None = None,
        execution_state: dict | None = None,
        evaluation: dict | None = None,
        transcript_messages: list | None = None,
    ):
        jd_analysis = self.jd_analysis_repo.get_latest_by_project_id(project_id)
        resume_profile = self.resume_profile_repo.get_latest_by_project_id(project_id)
        gap_analysis = self.gap_repo.get_latest_by_project_id(project_id)
        candidate_profile = self.candidate_profile_repo.get_latest_by_project_id(project_id)
        evidence_packet = self.evidence_builder.build_resume_packet(
            task="resume_authenticity_check",
            project_id=project_id,
            resume_profile=resume_profile.content if resume_profile else None,
            execution_state=execution_state,
            transcript_messages=transcript_messages or [],
        )
        definition = prompt_registry.get("resume_authenticity")
        input_snapshot = {
            "resume_id": resume_id,
            "has_resume_profile": bool(resume_profile),
            "has_jd_analysis": bool(jd_analysis),
            "has_gap_analysis": bool(gap_analysis),
            "has_project_candidate_profile": bool(candidate_profile),
            "evidence_packet": evidence_packet,
        }
        context_refs = {
            "resume_profile_id": resume_profile.id if resume_profile else None,
            "jd_analysis_id": jd_analysis.id if jd_analysis else None,
            "gap_analysis_id": gap_analysis.id if gap_analysis else None,
            "project_candidate_profile_id": candidate_profile.id if candidate_profile else None,
        }
        try:
            content, raw_response = await self.llm.generate_resume_authenticity_report(
                resume_content=resume_content,
                resume_profile=resume_profile.content if resume_profile else None,
                jd_analysis=jd_analysis.content if jd_analysis else None,
                gap_analysis=gap_analysis.content if gap_analysis else None,
                project_candidate_profile=candidate_profile.content if candidate_profile else None,
                execution_state=execution_state,
                evaluation=evaluation,
                transcript_messages=transcript_messages or [],
                evidence_packet=evidence_packet,
            )
        except Exception as exc:
            self.agent_run_recorder.record_failure(
                definition=definition,
                project_id=project_id,
                session_id=session_id,
                input_snapshot=input_snapshot,
                context_refs=context_refs,
                evidence_refs=self.evidence_builder.refs(evidence_packet),
                error=exc,
                model_name=self.llm.model,
            )
            self.db.commit()
            raise

        agent_run = self.agent_run_recorder.record_success(
            definition=definition,
            project_id=project_id,
            session_id=session_id,
            input_snapshot=input_snapshot,
            context_refs=context_refs,
            evidence_refs=self.evidence_builder.refs(evidence_packet),
            output_snapshot=content,
            raw_response=raw_response,
            model_name=self.llm.model,
        )
        return self.authenticity_repo.create(
            project_id=project_id,
            resume_id=resume_id,
            session_id=session_id,
            content=content,
            raw_response=raw_response,
            agent_run_id=agent_run.id,
            schema_version=definition.output_schema,
            evidence_refs=self.evidence_builder.refs(evidence_packet),
        )

    async def generate_resume_authenticity_for_latest_resume(
        self,
        project_id: int,
        session_id: int | None = None,
        execution_state: dict | None = None,
        evaluation: dict | None = None,
        transcript_messages: list | None = None,
    ):
        resume = self.resume_repo.get_latest_by_project_id(project_id)
        if not resume:
            return None
        return await self.generate_resume_authenticity_for_project(
            project_id=project_id,
            resume_id=resume.id,
            resume_content=resume.raw_content,
            session_id=session_id,
            execution_state=execution_state,
            evaluation=evaluation,
            transcript_messages=transcript_messages,
        )

    async def rewrite_resume_for_project(
        self,
        project_id: int,
        resume_id: int,
        resume_content: str,
        rewrite_mode: str,
        authenticity_report_id: int | None = None,
        resume_authenticity: dict | None = None,
        execution_state: dict | None = None,
        evaluation: dict | None = None,
        transcript_messages: list | None = None,
    ):
        jd_analysis = self.jd_analysis_repo.get_latest_by_project_id(project_id)
        resume_profile = self.resume_profile_repo.get_latest_by_project_id(project_id)
        gap_analysis = self.gap_repo.get_latest_by_project_id(project_id)
        candidate_profile = self.candidate_profile_repo.get_latest_by_project_id(project_id)
        evidence_packet = self.evidence_builder.build_resume_packet(
            task="resume_rewrite",
            project_id=project_id,
            resume_profile=resume_profile.content if resume_profile else None,
            execution_state=execution_state,
            transcript_messages=transcript_messages or [],
            authenticity_report=resume_authenticity,
        )
        definition = prompt_registry.get("resume_rewrite")
        input_snapshot = {
            "resume_id": resume_id,
            "rewrite_mode": rewrite_mode,
            "authenticity_report_id": authenticity_report_id,
            "has_resume_profile": bool(resume_profile),
            "has_jd_analysis": bool(jd_analysis),
            "has_gap_analysis": bool(gap_analysis),
            "has_project_candidate_profile": bool(candidate_profile),
            "evidence_packet": evidence_packet,
        }
        context_refs = {
            "resume_profile_id": resume_profile.id if resume_profile else None,
            "jd_analysis_id": jd_analysis.id if jd_analysis else None,
            "gap_analysis_id": gap_analysis.id if gap_analysis else None,
            "project_candidate_profile_id": candidate_profile.id if candidate_profile else None,
            "authenticity_report_id": authenticity_report_id,
        }
        try:
            content, raw_response = await self.llm.generate_resume_rewrite(
                rewrite_mode=rewrite_mode,
                resume_content=resume_content,
                resume_profile=resume_profile.content if resume_profile else None,
                jd_analysis=jd_analysis.content if jd_analysis else None,
                gap_analysis=gap_analysis.content if gap_analysis else None,
                project_candidate_profile=candidate_profile.content if candidate_profile else None,
                resume_authenticity=resume_authenticity,
                evaluation=evaluation,
                execution_state=execution_state,
                evidence_packet=evidence_packet,
            )
        except Exception as exc:
            self.agent_run_recorder.record_failure(
                definition=definition,
                project_id=project_id,
                session_id=None,
                input_snapshot=input_snapshot,
                context_refs=context_refs,
                evidence_refs=self.evidence_builder.refs(evidence_packet),
                error=exc,
                model_name=self.llm.model,
            )
            self.db.commit()
            raise

        agent_run = self.agent_run_recorder.record_success(
            definition=definition,
            project_id=project_id,
            session_id=None,
            input_snapshot=input_snapshot,
            context_refs=context_refs,
            evidence_refs=self.evidence_builder.refs(evidence_packet),
            output_snapshot=content,
            raw_response=raw_response,
            model_name=self.llm.model,
        )
        return self.rewrite_repo.create(
            project_id=project_id,
            resume_id=resume_id,
            rewrite_mode=rewrite_mode,
            authenticity_report_id=authenticity_report_id,
            content=content,
            raw_response=raw_response,
            agent_run_id=agent_run.id,
            schema_version=definition.output_schema,
            evidence_refs=self.evidence_builder.refs(evidence_packet),
        )

    def get_latest_interview_plan(self, project_uid: str):
        project = self._get_project(project_uid)
        plan = self.plan_repo.get_latest_by_project_id(project.id)
        if not plan:
            raise HTTPException(status_code=400, detail="Interview plan is required before starting interview")
        return project, plan

    def _get_project(self, project_uid: str):
        project = self.project_repo.get_by_uid(project_uid)
        if not project:
            raise HTTPException(status_code=404, detail="Preparation project not found")
        return project

    def _project_response(self, project) -> ProjectResponse:
        return ProjectResponse(
            projectId=project.project_uid,
            title=project.title,
            targetRole=project.target_role,
            status=project.status,
            createTime=project.create_time,
        )

    def _plan_mode(self, jd_analysis, resume_profile) -> str:
        if jd_analysis and resume_profile:
            return "jd_resume"
        if jd_analysis:
            return "jd_only"
        return "resume_only"

    def _jd_dict(self, jd) -> dict:
        return {
            "jdId": jd.id,
            "title": jd.title,
            "companyName": jd.company_name,
            "sourceUrl": jd.source_url,
            "status": jd.status,
        }

    def _resume_dict(self, resume) -> dict:
        return {
            "resumeId": resume.id,
            "fileName": resume.file_name,
            "fileType": resume.file_type,
            "status": resume.status,
        }

    def _latest_interview_context(self, project_id: int):
        session = self.interview_session_repo.get_latest_by_project_id(project_id)
        execution = self.interview_execution_repo.get_latest_by_session_id(session.id) if session else None
        evaluation = self.interview_evaluation_repo.get_latest_by_session_id(session.id) if session else None
        messages = self.interview_message_repo.list_by_session_id(session.id) if session else []
        return session, execution, evaluation, messages

    def _evaluation_dict(self, evaluation) -> dict:
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
