from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.preparation import (
    GapAnalysis,
    InterviewPlan,
    JDAnalysis,
    JobDescription,
    PreparationProject,
    ProjectCandidateProfile,
    ResumeAuthenticityReport,
    ResumeDocument,
    ResumeProfile,
    ResumeRewriteResult,
)


class BaseProjectRepository:
    model = None

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, item_id: int):
        statement = select(self.model).where(
            self.model.id == item_id,
            self.model.status != "deleted",
        )
        return self.db.scalars(statement).first()

    def get_latest_by_project_id(self, project_id: int):
        statement = (
            select(self.model)
            .where(
                self.model.project_id == project_id,
                self.model.status != "deleted",
            )
            .order_by(self.model.id.desc())
        )
        return self.db.scalars(statement).first()

    def list_by_project_id(self, project_id: int) -> list[Any]:
        statement = (
            select(self.model)
            .where(
                self.model.project_id == project_id,
                self.model.status != "deleted",
            )
            .order_by(self.model.id.desc())
        )
        return list(self.db.scalars(statement).all())

    def soft_delete(self, item):
        item.status = "deleted"
        self.db.flush()
        return item


class PreparationProjectRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, project_uid: str, title: str, target_role: str | None = None) -> PreparationProject:
        project = PreparationProject(
            project_uid=project_uid,
            title=title,
            target_role=target_role,
            status="active",
        )
        self.db.add(project)
        self.db.flush()
        return project

    def get_by_uid(self, project_uid: str) -> PreparationProject | None:
        statement = select(PreparationProject).where(
            PreparationProject.project_uid == project_uid,
            PreparationProject.status != "deleted",
        )
        return self.db.scalars(statement).first()

    def soft_delete(self, project: PreparationProject) -> PreparationProject:
        project.status = "deleted"
        self.db.flush()
        return project


class JobDescriptionRepository(BaseProjectRepository):
    model = JobDescription

    def create(
        self,
        project_id: int,
        raw_content: str,
        title: str | None = None,
        company_name: str | None = None,
        source_url: str | None = None,
    ) -> JobDescription:
        item = JobDescription(
            project_id=project_id,
            title=title,
            company_name=company_name,
            source_url=source_url,
            raw_content=raw_content,
        )
        self.db.add(item)
        self.db.flush()
        return item


class JDAnalysisRepository(BaseProjectRepository):
    model = JDAnalysis

    def create(
        self,
        project_id: int,
        jd_id: int,
        content: dict,
        raw_response: dict | None = None,
    ) -> JDAnalysis:
        item = JDAnalysis(
            project_id=project_id,
            jd_id=jd_id,
            content=content,
            raw_response=raw_response,
        )
        self.db.add(item)
        self.db.flush()
        return item


class ResumeDocumentRepository(BaseProjectRepository):
    model = ResumeDocument

    def create(
        self,
        project_id: int,
        raw_content: str,
        file_name: str | None = None,
        file_type: str | None = None,
    ) -> ResumeDocument:
        item = ResumeDocument(
            project_id=project_id,
            file_name=file_name,
            file_type=file_type,
            raw_content=raw_content,
        )
        self.db.add(item)
        self.db.flush()
        return item


class ResumeProfileRepository(BaseProjectRepository):
    model = ResumeProfile

    def create(
        self,
        project_id: int,
        resume_id: int,
        content: dict,
        raw_response: dict | None = None,
    ) -> ResumeProfile:
        item = ResumeProfile(
            project_id=project_id,
            resume_id=resume_id,
            content=content,
            raw_response=raw_response,
        )
        self.db.add(item)
        self.db.flush()
        return item


class GapAnalysisRepository(BaseProjectRepository):
    model = GapAnalysis

    def create(
        self,
        project_id: int,
        jd_analysis_id: int,
        resume_profile_id: int,
        content: dict,
        raw_response: dict | None = None,
    ) -> GapAnalysis:
        item = GapAnalysis(
            project_id=project_id,
            jd_analysis_id=jd_analysis_id,
            resume_profile_id=resume_profile_id,
            content=content,
            raw_response=raw_response,
        )
        self.db.add(item)
        self.db.flush()
        return item


class InterviewPlanRepository(BaseProjectRepository):
    model = InterviewPlan

    def create(
        self,
        project_id: int,
        plan_mode: str,
        content: dict,
        jd_analysis_id: int | None = None,
        resume_profile_id: int | None = None,
        gap_analysis_id: int | None = None,
        raw_response: dict | None = None,
    ) -> InterviewPlan:
        item = InterviewPlan(
            project_id=project_id,
            jd_analysis_id=jd_analysis_id,
            resume_profile_id=resume_profile_id,
            gap_analysis_id=gap_analysis_id,
            plan_mode=plan_mode,
            content=content,
            raw_response=raw_response,
        )
        self.db.add(item)
        self.db.flush()
        return item


class ProjectCandidateProfileRepository(BaseProjectRepository):
    model = ProjectCandidateProfile

    def create(
        self,
        project_id: int,
        content: dict,
        source_session_id: int | None = None,
        raw_response: dict | None = None,
    ) -> ProjectCandidateProfile:
        item = ProjectCandidateProfile(
            project_id=project_id,
            source_session_id=source_session_id,
            content=content,
            raw_response=raw_response,
        )
        self.db.add(item)
        self.db.flush()
        return item


class ResumeAuthenticityReportRepository(BaseProjectRepository):
    model = ResumeAuthenticityReport

    def create(
        self,
        project_id: int,
        resume_id: int,
        content: dict,
        session_id: int | None = None,
        raw_response: dict | None = None,
    ) -> ResumeAuthenticityReport:
        item = ResumeAuthenticityReport(
            project_id=project_id,
            resume_id=resume_id,
            session_id=session_id,
            content=content,
            raw_response=raw_response,
        )
        self.db.add(item)
        self.db.flush()
        return item


class ResumeRewriteResultRepository(BaseProjectRepository):
    model = ResumeRewriteResult

    def create(
        self,
        project_id: int,
        resume_id: int,
        rewrite_mode: str,
        content: dict,
        authenticity_report_id: int | None = None,
        raw_response: dict | None = None,
    ) -> ResumeRewriteResult:
        item = ResumeRewriteResult(
            project_id=project_id,
            resume_id=resume_id,
            authenticity_report_id=authenticity_report_id,
            rewrite_mode=rewrite_mode,
            content=content,
            raw_response=raw_response,
        )
        self.db.add(item)
        self.db.flush()
        return item
