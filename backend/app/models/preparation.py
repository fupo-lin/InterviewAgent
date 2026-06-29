from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.mysql import JSON, MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.config.database import Base


class PreparationProject(Base):
    __tablename__ = "preparation_projects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_uid: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    target_role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class JobDescription(Base):
    __tablename__ = "job_descriptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("preparation_projects.id"), nullable=False)
    title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_content: Mapped[str] = mapped_column(MEDIUMTEXT, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class JDAnalysis(Base):
    __tablename__ = "jd_analyses"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("preparation_projects.id"), nullable=False)
    jd_id: Mapped[int] = mapped_column(ForeignKey("job_descriptions.id"), nullable=False)
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    raw_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class ResumeDocument(Base):
    __tablename__ = "resume_documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("preparation_projects.id"), nullable=False)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    raw_content: Mapped[str] = mapped_column(MEDIUMTEXT, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ResumeProfile(Base):
    __tablename__ = "resume_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("preparation_projects.id"), nullable=False)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resume_documents.id"), nullable=False)
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    raw_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class GapAnalysis(Base):
    __tablename__ = "gap_analyses"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("preparation_projects.id"), nullable=False)
    jd_analysis_id: Mapped[int] = mapped_column(ForeignKey("jd_analyses.id"), nullable=False)
    resume_profile_id: Mapped[int] = mapped_column(ForeignKey("resume_profiles.id"), nullable=False)
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    raw_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class InterviewPlan(Base):
    __tablename__ = "interview_plans"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("preparation_projects.id"), nullable=False)
    jd_analysis_id: Mapped[int | None] = mapped_column(ForeignKey("jd_analyses.id"), nullable=True)
    resume_profile_id: Mapped[int | None] = mapped_column(ForeignKey("resume_profiles.id"), nullable=True)
    gap_analysis_id: Mapped[int | None] = mapped_column(ForeignKey("gap_analyses.id"), nullable=True)
    plan_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    raw_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ProjectCandidateProfile(Base):
    __tablename__ = "project_candidate_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("preparation_projects.id"), nullable=False)
    source_session_id: Mapped[int | None] = mapped_column(ForeignKey("interview_sessions.id"), nullable=True)
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    raw_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class ResumeAuthenticityReport(Base):
    __tablename__ = "resume_authenticity_reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("preparation_projects.id"), nullable=False)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resume_documents.id"), nullable=False)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("interview_sessions.id"), nullable=True)
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    raw_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class ResumeRewriteResult(Base):
    __tablename__ = "resume_rewrite_results"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("preparation_projects.id"), nullable=False)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resume_documents.id"), nullable=False)
    authenticity_report_id: Mapped[int | None] = mapped_column(
        ForeignKey("resume_authenticity_reports.id"),
        nullable=True,
    )
    rewrite_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    raw_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
