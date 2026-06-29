from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.repository.preparation_repository import (
    GapAnalysisRepository,
    InterviewPlanRepository,
    JDAnalysisRepository,
    JobDescriptionRepository,
    PreparationProjectRepository,
    ResumeDocumentRepository,
    ResumeProfileRepository,
)
from app.schemas.preparation import (
    AnalysisResponse,
    GapAnalysisResponse,
    InterviewPlanResponse,
    JobDescriptionResponse,
    ProjectOverviewResponse,
    ProjectResponse,
    ResumeDocumentResponse,
    ResumeProfileResponse,
)
from app.service.llm_service import LLMService


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
        self.llm = LLMService()

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

        content, raw_response = await self.llm.generate_jd_analysis(jd.raw_content)
        saved = self.jd_analysis_repo.create(
            project_id=project.id,
            jd_id=jd.id,
            content=content,
            raw_response=raw_response,
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

        content, raw_response = await self.llm.generate_resume_profile(resume.raw_content)
        saved = self.resume_profile_repo.create(
            project_id=project.id,
            resume_id=resume.id,
            content=content,
            raw_response=raw_response,
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
