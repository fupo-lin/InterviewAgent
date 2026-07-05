from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from app.service.post_interview_assessment_nodes import PostInterviewAssessmentNodes
from app.service.post_interview_assessment_state import PostInterviewAssessmentState


@dataclass(frozen=True)
class PostInterviewAssessmentResult:
    evaluation: object | None
    state: PostInterviewAssessmentState


class PostInterviewAssessmentWorkflow:
    def __init__(
        self,
        nodes: PostInterviewAssessmentNodes,
        runtime=None,
    ) -> None:
        self.nodes = nodes
        self.runtime = runtime

    async def run(
        self,
        session,
        incoming_trigger: str = "interview_end",
    ) -> PostInterviewAssessmentResult:
        workflow_run, state = self._state_for_run(session, incoming_trigger)
        try:
            self._save(workflow_run, state, "start", "running")

            state["active_step"] = "load_assessment_context"
            context = self.nodes.load_context_node(state, session)
            self._save(workflow_run, state, "load_assessment_context", "running")

            state["active_step"] = "ensure_evaluation"
            evaluation = await self.nodes.ensure_evaluation_node(state, session, context)
            self._save(workflow_run, state, "ensure_evaluation", "running")

            state["active_step"] = "complete"
            self.nodes.complete_node(state, session)
            self._save(workflow_run, state, "complete", self._final_status(state))
        except Exception as exc:
            self._fail(workflow_run, state, self._failed_step_id(state), exc)
            raise
        return PostInterviewAssessmentResult(
            evaluation=evaluation,
            state=state,
        )

    def record_project_outputs(
        self,
        result: PostInterviewAssessmentResult,
        *,
        project_candidate_profile_id: int | None = None,
        resume_authenticity_report_id: int | None = None,
    ) -> None:
        self.nodes.record_project_outputs(
            result.state,
            project_candidate_profile_id=project_candidate_profile_id,
            resume_authenticity_report_id=resume_authenticity_report_id,
        )
        workflow_run = self._load_workflow_run(result.state)
        self._save(
            workflow_run,
            result.state,
            "complete",
            result.state.get("status") or "success",
        )

    def _state_for_run(
        self,
        session,
        incoming_trigger: str,
    ) -> tuple[object | None, PostInterviewAssessmentState]:
        initial_state = self.nodes.initial_state(session, incoming_trigger)
        workflow_run = self._load_or_create_workflow_run(session, initial_state)
        if not workflow_run:
            return None, initial_state
        stored_state = dict(getattr(workflow_run, "state", None) or {})
        workflow_status = getattr(workflow_run, "status", None)
        current_step = getattr(workflow_run, "current_step", None)
        state: PostInterviewAssessmentState = {
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
            "resume_reason": self._resume_reason(workflow_status),
            "resume_from_step": current_step,
            "branch": None,
            "branch_reason": None,
            "branch_decisions": [],
            "output_contract_version": initial_state["output_contract_version"],
            "outputs": initial_state["outputs"],
            "next_actions": [],
        }
        state["workflow_run_id"] = workflow_run.workflow_run_id
        return workflow_run, state

    def _load_or_create_workflow_run(
        self,
        session,
        state: PostInterviewAssessmentState,
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

    def _load_workflow_run(self, state: PostInterviewAssessmentState):
        if not self.runtime or not state.get("workflow_run_id"):
            return None
        repository = getattr(self.runtime, "repository", None)
        if not repository:
            return None
        return repository.get_by_workflow_run_id(state["workflow_run_id"])

    def _save(
        self,
        workflow_run,
        state: PostInterviewAssessmentState,
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
        state: PostInterviewAssessmentState,
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

    def _failed_step_id(self, state: PostInterviewAssessmentState) -> str:
        if state.get("last_error") and state["last_error"].get("step_id"):
            return state["last_error"]["step_id"]
        if state.get("active_step"):
            return state["active_step"]
        completed = state.get("completed_steps") or []
        if "load_assessment_context" not in completed:
            return "load_assessment_context"
        if "ensure_evaluation" not in completed and "ensure_evaluation_reused" not in completed:
            return "ensure_evaluation"
        return "unknown"

    def _final_status(self, state: PostInterviewAssessmentState) -> str:
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
