from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.workflow import WorkflowRun


class WorkflowRunRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_thread_id(self, thread_id: str) -> WorkflowRun | None:
        statement = select(WorkflowRun).where(WorkflowRun.thread_id == thread_id)
        return self.db.scalars(statement).first()

    def get_by_workflow_run_id(self, workflow_run_id: str) -> WorkflowRun | None:
        statement = select(WorkflowRun).where(
            WorkflowRun.workflow_run_id == workflow_run_id,
        )
        return self.db.scalars(statement).first()

    def list(
        self,
        workflow_id: str | None = None,
        project_id: int | None = None,
        session_id: int | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[WorkflowRun]:
        statement = select(WorkflowRun)
        if workflow_id:
            statement = statement.where(WorkflowRun.workflow_id == workflow_id)
        if project_id is not None:
            statement = statement.where(WorkflowRun.project_id == project_id)
        if session_id is not None:
            statement = statement.where(WorkflowRun.session_id == session_id)
        if status:
            statement = statement.where(WorkflowRun.status == status)
        statement = statement.order_by(WorkflowRun.update_time.desc()).limit(limit)
        return list(self.db.scalars(statement).all())

    def create(
        self,
        *,
        workflow_run_id: str,
        workflow_id: str,
        thread_id: str,
        project_id: int | None,
        session_id: int | None,
        status: str = "running",
        current_step: str | None = None,
        state: dict | None = None,
    ) -> WorkflowRun:
        item = WorkflowRun(
            workflow_run_id=workflow_run_id,
            workflow_id=workflow_id,
            thread_id=thread_id,
            project_id=project_id,
            session_id=session_id,
            status=status,
            current_step=current_step,
            state=state or {},
        )
        self.db.add(item)
        self.db.flush()
        return item

    def save_state(
        self,
        item: WorkflowRun,
        *,
        state: dict,
        current_step: str | None = None,
        status: str | None = None,
        last_error: dict | None = None,
        error_message: str | None = None,
    ) -> WorkflowRun:
        item.state = state
        if current_step is not None:
            item.current_step = current_step
        if status is not None:
            item.status = status
        item.last_error = last_error
        item.error_message = error_message
        flag_modified(item, "state")
        if last_error is not None:
            flag_modified(item, "last_error")
        self.db.flush()
        return item
