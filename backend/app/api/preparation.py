from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.schemas.preparation import (
    AnalysisResponse,
    GapAnalysisResponse,
    InterviewPlanResponse,
    JobDescriptionRequest,
    JobDescriptionResponse,
    ProjectCreateRequest,
    ProjectInterviewStartResponse,
    ProjectOverviewResponse,
    ProjectResponse,
    ResumeDocumentRequest,
    ResumeDocumentResponse,
    ResumeProfileResponse,
)
from app.service.interview_service import InterviewService
from app.service.preparation_service import PreparationService

router = APIRouter(prefix="/preparation", tags=["preparation"])


@router.post("/projects", response_model=ProjectResponse, response_model_by_alias=True)
def create_project(payload: ProjectCreateRequest, db: Session = Depends(get_db)):
    service = PreparationService(db)
    return service.create_project(payload.title, payload.target_role)


@router.get("/projects/{project_id}/overview", response_model=ProjectOverviewResponse, response_model_by_alias=True)
def get_project_overview(project_id: str, db: Session = Depends(get_db)):
    service = PreparationService(db)
    return service.overview(project_id)


@router.post("/projects/{project_id}/jd", response_model=JobDescriptionResponse, response_model_by_alias=True)
def add_jd(project_id: str, payload: JobDescriptionRequest, db: Session = Depends(get_db)):
    service = PreparationService(db)
    return service.add_jd(
        project_uid=project_id,
        content=payload.content,
        title=payload.title,
        company_name=payload.company_name,
        source_url=payload.source_url,
    )


@router.post("/projects/{project_id}/jd/analyze", response_model=AnalysisResponse, response_model_by_alias=True)
async def analyze_jd(project_id: str, db: Session = Depends(get_db)):
    service = PreparationService(db)
    return await service.analyze_jd(project_id)


@router.post("/projects/{project_id}/resume", response_model=ResumeDocumentResponse, response_model_by_alias=True)
def add_resume(project_id: str, payload: ResumeDocumentRequest, db: Session = Depends(get_db)):
    service = PreparationService(db)
    return service.add_resume(
        project_uid=project_id,
        content=payload.content,
        file_name=payload.file_name,
        file_type=payload.file_type,
    )


@router.post(
    "/projects/{project_id}/resume/analyze",
    response_model=ResumeProfileResponse,
    response_model_by_alias=True,
)
async def analyze_resume(project_id: str, db: Session = Depends(get_db)):
    service = PreparationService(db)
    return await service.analyze_resume(project_id)


@router.post("/projects/{project_id}/gap/analyze", response_model=GapAnalysisResponse, response_model_by_alias=True)
async def analyze_gap(project_id: str, db: Session = Depends(get_db)):
    service = PreparationService(db)
    return await service.analyze_gap(project_id)


@router.post(
    "/projects/{project_id}/interview-plan/generate",
    response_model=InterviewPlanResponse,
    response_model_by_alias=True,
)
async def generate_interview_plan(project_id: str, db: Session = Depends(get_db)):
    service = PreparationService(db)
    return await service.generate_interview_plan(project_id)


@router.post(
    "/projects/{project_id}/interview/start",
    response_model=ProjectInterviewStartResponse,
    response_model_by_alias=True,
)
async def start_project_interview(project_id: str, db: Session = Depends(get_db)):
    service = InterviewService(db)
    session_id, reply = await service.start_with_project(project_id)
    return ProjectInterviewStartResponse(sessionId=session_id, reply=reply)
