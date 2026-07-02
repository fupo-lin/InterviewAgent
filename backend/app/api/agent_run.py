from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.schemas.agent_run import AgentRunDetailResponse, AgentRunListResponse
from app.service.agent_run_query_service import AgentRunQueryService

router = APIRouter(prefix="/agent-runs", tags=["agent-runs"])


@router.get("", response_model=AgentRunListResponse, response_model_by_alias=True)
def list_agent_runs(
    project_id: int | None = Query(default=None, alias="projectId"),
    session_id: int | None = Query(default=None, alias="sessionId"),
    status: str | None = None,
    agent_name: str | None = Query(default=None, alias="agentName"),
    prompt_id: str | None = Query(default=None, alias="promptId"),
    workflow_id: str | None = Query(default=None, alias="workflowId"),
    workflow_run_id: str | None = Query(default=None, alias="workflowRunId"),
    workflow_step_id: str | None = Query(default=None, alias="workflowStepId"),
    only_issues: bool = Query(default=False, alias="onlyIssues"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    service = AgentRunQueryService(db)
    return service.list_runs(
        project_id=project_id,
        session_id=session_id,
        status=status,
        agent_name=agent_name,
        prompt_id=prompt_id,
        workflow_id=workflow_id,
        workflow_run_id=workflow_run_id,
        workflow_step_id=workflow_step_id,
        only_issues=only_issues,
        limit=limit,
    )


@router.get("/failed", response_model=AgentRunListResponse, response_model_by_alias=True)
def list_failed_agent_runs(
    project_id: int | None = Query(default=None, alias="projectId"),
    session_id: int | None = Query(default=None, alias="sessionId"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    service = AgentRunQueryService(db)
    return service.failed_runs(project_id=project_id, session_id=session_id, limit=limit)


@router.get("/{agent_run_id}", response_model=AgentRunDetailResponse, response_model_by_alias=True)
def get_agent_run(agent_run_id: int, db: Session = Depends(get_db)):
    service = AgentRunQueryService(db)
    return service.get_detail(agent_run_id)
