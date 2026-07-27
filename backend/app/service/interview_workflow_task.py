from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from app.service.workflow_runtime import WorkflowRuntime


@dataclass(frozen=True)
class InterviewWorkflowTask:
    workflow_run_id: str
    session_uid: str
    session_id: int
    status: str


class InterviewWorkflowTaskService:
    def __init__(self, db, session_repo=None, workflow_repo=None) -> None:
        self.db = db
        if session_repo is None or workflow_repo is None:
            from app.repository.interview_repository import InterviewSessionRepository
            from app.repository.workflow_run_repository import WorkflowRunRepository

        self.session_repo = session_repo or InterviewSessionRepository(db)
        self.workflow_repo = workflow_repo or WorkflowRunRepository(db)
        self.workflow_runtime = WorkflowRuntime(self.workflow_repo)

    def enqueue_user_message(self, session_uid: str, message: str) -> InterviewWorkflowTask:
        session = self.session_repo.get_by_uid(session_uid)
        if not session:
            raise HTTPException(status_code=404, detail="Interview session not found")
        if session.status != "active":
            raise HTTPException(status_code=400, detail="Interview session is not active")

        existing = self.workflow_repo.get_by_thread_id(f"interview:{session.session_uid}")
        if existing and existing.status in {"failed", "running", "queued"}:
            status = "queued_retry" if existing.status == "failed" else "queued_recovery"
            self._mark_recovery_task(existing, session, status)
            self.db.commit()
            return InterviewWorkflowTask(
                workflow_run_id=existing.workflow_run_id,
                session_uid=session.session_uid,
                session_id=session.id,
                status=status,
            )

        initial_state = {
            "workflow_id": "interview_runtime",
            "thread_id": f"interview:{session.session_uid}",
            "status": "queued",
            "active_step": None,
            "project_id": session.project_id,
            "session_id": session.id,
            "session_uid": session.session_uid,
            "role_name": session.role_name,
            "interview_plan_id": session.interview_plan_id,
            "incoming_user_input": message,
            "current_section_index": 0,
            "current_section_round_no": 0,
            "total_completed_round_no": 0,
            "completed_steps": [],
            "failed_steps": [],
            "last_memory_agent_run_ids": [],
            "last_error": None,
            "task": {
                "type": "interview_user_message",
                "status": "queued",
                "queued_at": self._timestamp(),
                "message": message,
            },
        }
        workflow_run = self.workflow_runtime.load_or_create(
            workflow_id="interview_runtime",
            thread_id=initial_state["thread_id"],
            project_id=session.project_id,
            session_id=session.id,
            initial_state=initial_state,
        )
        state = dict(workflow_run.state or {})
        state.update(
            {
                **initial_state,
                "workflow_run_id": workflow_run.workflow_run_id,
                "incoming_user_input": message,
            }
        )
        self.workflow_runtime.save(
            workflow_run,
            state=state,
            current_step="workflow_task",
            status="queued",
            last_error=None,
        )
        self.db.commit()
        return InterviewWorkflowTask(
            workflow_run_id=workflow_run.workflow_run_id,
            session_uid=session.session_uid,
            session_id=session.id,
            status="queued",
        )

    def _mark_recovery_task(self, workflow_run, session, status: str) -> None:
        state = dict(workflow_run.state or {})
        task = state.setdefault("task", {})
        if isinstance(task, dict):
            task["type"] = "interview_user_message"
            task["status"] = status
            task["queued_at"] = self._timestamp()
            task["recovery_from_status"] = workflow_run.status
        self.workflow_repo.save_state(
            workflow_run,
            state=state,
            current_step=workflow_run.current_step or "workflow_task",
            status=workflow_run.status,
            last_error=workflow_run.last_error,
            error_message=workflow_run.error_message,
        )
        workflow_run.project_id = session.project_id
        workflow_run.session_id = session.id

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()


class InterviewWorkflowWorker:
    def __init__(self, session_factory=None) -> None:
        self.session_factory = session_factory

    def submit(self, session_uid: str, message: str) -> None:
        asyncio.create_task(self.run_once(session_uid, message))

    async def run_once(self, session_uid: str, message: str) -> dict[str, Any]:
        db = self._session_factory()()
        try:
            from app.service.interview_service import InterviewService

            service = InterviewService(db)
            reply, round_no = await service.chat(session_uid, message)
            return {"status": "success", "reply": reply, "round_no": round_no}
        except Exception as exc:
            db.rollback()
            self._record_worker_failure(db, session_uid, exc)
            db.commit()
            return {
                "status": "failed",
                "error": str(exc),
                "error_type": exc.__class__.__name__,
            }
        finally:
            db.close()

    def _record_worker_failure(self, db, session_uid: str, exc: Exception) -> None:
        from app.repository.interview_repository import InterviewSessionRepository
        from app.repository.workflow_run_repository import WorkflowRunRepository

        session_repo = InterviewSessionRepository(db)
        workflow_repo = WorkflowRunRepository(db)
        workflow_run = workflow_repo.get_by_thread_id(f"interview:{session_uid}")
        session = session_repo.get_by_uid(session_uid)
        if not workflow_run:
            return
        state = dict(workflow_run.state or {})
        failed_steps = state.setdefault("failed_steps", [])
        if "worker" not in failed_steps:
            failed_steps.append("worker")
        state["status"] = "failed"
        state["active_step"] = None
        state["last_error"] = {
            "step_id": state.get("active_step") or "worker",
            "message": str(exc),
            "error_type": exc.__class__.__name__,
        }
        task = state.setdefault("task", {})
        if isinstance(task, dict):
            task["status"] = "failed"
            task["failed_at"] = datetime.now(timezone.utc).isoformat()
        workflow_repo.save_state(
            workflow_run,
            state=state,
            current_step=state["last_error"]["step_id"],
            status="failed",
            last_error=state["last_error"],
            error_message=str(exc),
        )
        if session:
            workflow_run.project_id = session.project_id
            workflow_run.session_id = session.id

    def _session_factory(self):
        if self.session_factory:
            return self.session_factory
        from app.config.database import SessionLocal

        return SessionLocal


interview_workflow_worker = InterviewWorkflowWorker()
