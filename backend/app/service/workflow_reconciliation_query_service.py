from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.repository.agent_run_repository import AgentRunRepository
from app.repository.interview_repository import (
    InterviewMessageRepository,
    InterviewPlanExecutionRepository,
)
from app.repository.workflow_run_repository import WorkflowRunRepository
from app.service.workflow_checkpoint_reconciliation import (
    WorkflowCheckpointReconciliationService,
)


class WorkflowReconciliationQueryService:
    def __init__(self, db: Any) -> None:
        self.workflow_repo = WorkflowRunRepository(db)
        self.reconciliation = WorkflowCheckpointReconciliationService(
            message_repo=InterviewMessageRepository(db),
            agent_run_repo=AgentRunRepository(db),
            execution_repo=InterviewPlanExecutionRepository(db),
        )

    def get_reconciliation(self, workflow_run_id: str) -> dict:
        workflow_run = self.workflow_repo.get_by_workflow_run_id(workflow_run_id)
        if not workflow_run:
            raise HTTPException(status_code=404, detail="Workflow run not found")
        return self.reconciliation.reconcile(workflow_run).to_dict()
