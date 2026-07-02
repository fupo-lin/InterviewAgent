from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.schemas.workflow_run import WorkflowRunDetailResponse, WorkflowRunListResponse
from app.service.workflow_run_query_service import WorkflowRunQueryService

router = APIRouter(prefix="/workflow-runs", tags=["workflow-runs"])


@router.get("", response_model=WorkflowRunListResponse, response_model_by_alias=True)
def list_workflow_runs(
    workflow_id: str | None = Query(default=None, alias="workflowId"),
    project_id: int | None = Query(default=None, alias="projectId"),
    session_id: int | None = Query(default=None, alias="sessionId"),
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    service = WorkflowRunQueryService(db)
    return service.list_runs(
        workflow_id=workflow_id,
        project_id=project_id,
        session_id=session_id,
        status=status,
        limit=limit,
    )


@router.get("/{workflow_run_id}", response_model=WorkflowRunDetailResponse, response_model_by_alias=True)
def get_workflow_run(workflow_run_id: str, db: Session = Depends(get_db)):
    service = WorkflowRunQueryService(db)
    return service.get_detail(workflow_run_id)
