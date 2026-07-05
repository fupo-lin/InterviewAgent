from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from app.service.candidate_growth_report_nodes import CandidateGrowthReportNodes
from app.service.candidate_growth_report_state import CandidateGrowthReportState


@dataclass(frozen=True)
class CandidateGrowthReportResult:
    report: object | None
    state: CandidateGrowthReportState


class CandidateGrowthReportWorkflow:
    def __init__(
        self,
        nodes: CandidateGrowthReportNodes,
        runtime=None,
    ) -> None:
        self.nodes = nodes
        self.runtime = runtime

    async def run(
        self,
        session,
        incoming_trigger: str = "manual_generate",
    ) -> CandidateGrowthReportResult:
        workflow_run, state = self._state_for_run(session, incoming_trigger)
        report = None
        try:
            self._save(workflow_run, state, "start", "running")

            state["active_step"] = "load_growth_context"
            context = self.nodes.load_context_node(state, session)
            self._save(workflow_run, state, "load_growth_context", "running")

            state["active_step"] = "build_growth_evidence"
            context = self.nodes.build_evidence_node(state, session, context)
            self._save(workflow_run, state, "build_growth_evidence", "running")

            state["active_step"] = "ensure_growth_report"
            context = self.nodes.ensure_report_node(state, context)
            self._save(workflow_run, state, "ensure_growth_report", "running")

            state["active_step"] = "generate_growth_report"
            context = await self.nodes.generate_report_node(state, session, context)
            self._save(workflow_run, state, "generate_growth_report", "running")

            state["active_step"] = "persist_growth_report"
            report = self.nodes.persist_report_node(state, session, context)
            self._save(workflow_run, state, "persist_growth_report", "running")

            state["active_step"] = "complete"
            self.nodes.complete_node(state)
            self._save(workflow_run, state, "complete", self._final_status(state))
        except Exception as exc:
            self._fail(workflow_run, state, self._failed_step_id(state), exc)
            raise
        return CandidateGrowthReportResult(report=report, state=state)

    def _state_for_run(
        self,
        session,
        incoming_trigger: str,
    ) -> tuple[object | None, CandidateGrowthReportState]:
        initial_state = self.nodes.initial_state(session, incoming_trigger)
        workflow_run = self._load_or_create_workflow_run(session, initial_state)
        if not workflow_run:
            return None, initial_state
        stored_state = dict(getattr(workflow_run, "state", None) or {})
        workflow_status = getattr(workflow_run, "status", None)
        current_step = getattr(workflow_run, "current_step", None)
        state: CandidateGrowthReportState = {
            **initial_state,
            **stored_state,
            "workflow_id": initial_state["workflow_id"],
            "thread_id": initial_state["thread_id"],
            "project_id": session.project_id,
            "session_id": session.id,
            "session_uid": session.session_uid,
            "incoming_trigger": stored_state.get("incoming_trigger") or incoming_trigger,
            "status": "running",
            "active_step": None,
            "completed_steps": [],
            "skipped_steps": [],
            "failed_steps": [],
            "last_error": None,
            "partial_reason": None,
            "missing_inputs": [],
            "resume_reason": self._resume_reason(workflow_status),
            "resume_from_step": current_step,
            "branch": None,
            "branch_reason": None,
            "branch_decisions": [],
            "outputs": initial_state["outputs"],
            "next_actions": [],
        }
        state["workflow_run_id"] = workflow_run.workflow_run_id
        return workflow_run, state

    def _load_or_create_workflow_run(
        self,
        session,
        state: CandidateGrowthReportState,
    ):
        if not self.runtime:
            return None
        return self.runtime.load_or_create(
            workflow_id=state["workflow_id"],
            thread_id=state["thread_id"],
            project_id=session.project_id,
            session_id=session.id,
            initial_state=state,
        )

    def _save(
        self,
        workflow_run,
        state: CandidateGrowthReportState,
        current_step: str,
        status: str,
    ) -> None:
        if not self.runtime or not workflow_run:
            return
        state["status"] = status
        self.runtime.save(
            workflow_run,
            state=deepcopy(dict(state)),
            current_step=current_step,
            status=status,
            last_error=state.get("last_error"),
        )

    def _fail(
        self,
        workflow_run,
        state: CandidateGrowthReportState,
        current_step: str,
        exc: Exception,
    ) -> None:
        failed_steps = state.setdefault("failed_steps", [])
        if current_step not in failed_steps:
            failed_steps.append(current_step)
        state["last_error"] = {
            "step_id": current_step,
            "message": str(exc),
            "error_type": exc.__class__.__name__,
        }
        self._save(workflow_run, state, current_step, "failed")

    def _failed_step_id(self, state: CandidateGrowthReportState) -> str:
        if state.get("last_error") and state["last_error"].get("step_id"):
            return state["last_error"]["step_id"]
        if state.get("active_step"):
            return state["active_step"]
        return "unknown"

    def _final_status(self, state: CandidateGrowthReportState) -> str:
        if state.get("partial_reason"):
            return "partial"
        return "success"

    def _resume_reason(self, workflow_status: str | None) -> str:
        if workflow_status == "failed":
            return "failed_retry"
        if workflow_status == "running":
            return "unfinished_run"
        if workflow_status == "success":
            return "already_completed"
        return "new_trigger"
