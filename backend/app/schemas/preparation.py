from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ProjectCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    target_role: str | None = Field(default=None, alias="targetRole", max_length=100)


class ProjectResponse(BaseModel):
    project_uid: str = Field(alias="projectId")
    title: str
    target_role: str | None = Field(default=None, alias="targetRole")
    status: str
    create_time: datetime = Field(alias="createTime")

    class Config:
        populate_by_name = True


class JobDescriptionRequest(BaseModel):
    content: str = Field(min_length=1)
    title: str | None = Field(default=None, max_length=100)
    company_name: str | None = Field(default=None, alias="companyName", max_length=100)
    source_url: str | None = Field(default=None, alias="sourceUrl", max_length=500)


class JobDescriptionResponse(BaseModel):
    jd_id: int = Field(alias="jdId")
    title: str | None = None
    company_name: str | None = Field(default=None, alias="companyName")
    source_url: str | None = Field(default=None, alias="sourceUrl")
    status: str

    class Config:
        populate_by_name = True


class ResumeDocumentRequest(BaseModel):
    content: str = Field(min_length=1)
    file_name: str | None = Field(default=None, alias="fileName", max_length=255)
    file_type: str | None = Field(default="text", alias="fileType", max_length=30)


class ResumeDocumentResponse(BaseModel):
    resume_id: int = Field(alias="resumeId")
    file_name: str | None = Field(default=None, alias="fileName")
    file_type: str | None = Field(default=None, alias="fileType")
    status: str

    class Config:
        populate_by_name = True


class AnalysisResponse(BaseModel):
    analysis_id: int = Field(alias="analysisId")
    analysis: dict[str, Any]

    class Config:
        populate_by_name = True


class ResumeProfileResponse(BaseModel):
    profile_id: int = Field(alias="profileId")
    profile: dict[str, Any]

    class Config:
        populate_by_name = True


class GapAnalysisResponse(BaseModel):
    gap_analysis_id: int = Field(alias="gapAnalysisId")
    gap_analysis: dict[str, Any] = Field(alias="gapAnalysis")

    class Config:
        populate_by_name = True


class InterviewPlanResponse(BaseModel):
    interview_plan_id: int = Field(alias="interviewPlanId")
    plan_mode: str = Field(alias="planMode")
    plan: dict[str, Any]

    class Config:
        populate_by_name = True


class ProjectInterviewStartResponse(BaseModel):
    session_id: str = Field(alias="sessionId")
    reply: str

    class Config:
        populate_by_name = True


class ProjectCandidateProfileResponse(BaseModel):
    profile_id: int = Field(alias="profileId")
    profile_version_no: int = Field(alias="profileVersionNo")
    previous_profile_id: int | None = Field(default=None, alias="previousProfileId")
    is_current: bool = Field(alias="isCurrent")
    schema_version: str = Field(alias="schemaVersion")
    agent_run_id: int | None = Field(default=None, alias="agentRunId")
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")
    source_context_refs: dict[str, Any] = Field(default_factory=dict, alias="sourceContextRefs")
    profile: dict[str, Any]

    class Config:
        populate_by_name = True


class ResumeAuthenticityResponse(BaseModel):
    report_id: int = Field(alias="reportId")
    report: dict[str, Any]

    class Config:
        populate_by_name = True


class ResumeRewriteRequest(BaseModel):
    rewrite_mode: str = Field(default="jd_targeted", alias="rewriteMode", max_length=30)


class ResumeRewriteResponse(BaseModel):
    rewrite_id: int = Field(alias="rewriteId")
    rewrite_mode: str = Field(alias="rewriteMode")
    result: dict[str, Any]

    class Config:
        populate_by_name = True


class ProjectOverviewResponse(BaseModel):
    project: dict[str, Any]
    jd: dict[str, Any] | None = None
    jd_analysis: dict[str, Any] | None = Field(default=None, alias="jdAnalysis")
    resume: dict[str, Any] | None = None
    resume_profile: dict[str, Any] | None = Field(default=None, alias="resumeProfile")
    gap_analysis: dict[str, Any] | None = Field(default=None, alias="gapAnalysis")
    interview_plan: dict[str, Any] | None = Field(default=None, alias="interviewPlan")
    candidate_profile: dict[str, Any] | None = Field(default=None, alias="candidateProfile")
    resume_authenticity: dict[str, Any] | None = Field(default=None, alias="resumeAuthenticity")
    resume_rewrite: dict[str, Any] | None = Field(default=None, alias="resumeRewrite")

    class Config:
        populate_by_name = True
