from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass

from app.config.settings import settings
from app.service.interview_runtime_nodes import InterviewRuntimeNodes
from app.service.interview_runtime_resume import resume_interview_runtime_state
from app.service.interview_runtime_router import InterviewRuntimeRouter
from app.service.interview_runtime_state import InterviewRuntimeState


@dataclass(frozen=True)
class InterviewRuntimeWorkflowResult:
    reply: str
    round_no: int
    state: InterviewRuntimeState
    answer_message_id: int
    assistant_message_id: int


class InterviewRuntimeWorkflowError(RuntimeError):
    def __init__(
        self,
        step_id: str,
        message: str,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.step_id = step_id
        self.cause = cause


class InterviewRuntimeWorkflow:
    def __init__(
        self,
        nodes: InterviewRuntimeNodes,
        runtime=None,
        use_langgraph: bool | None = None,
        checkpointer=None,
        commit_after_step: Callable[[], None] | None = None,
    ) -> None:
        self.nodes = nodes
        self.runtime = runtime
        self.checkpointer = checkpointer
        self.commit_after_step = commit_after_step
        self.router = InterviewRuntimeRouter()
        self.use_langgraph = (
            settings.use_langgraph_interview_runtime
            if use_langgraph is None
            else use_langgraph
        )
        self._langgraph_runtime = None

    async def resume_with_user_input(
        self,
        session,
        message: str,
    ) -> InterviewRuntimeWorkflowResult:
        if self.use_langgraph:
            return await self._langgraph().resume_with_user_input(session, message)
        return await self._resume_sequential(session, message)

    async def _resume_sequential(
        self,
        session,
        message: str,
    ) -> InterviewRuntimeWorkflowResult:
        workflow_run, state = self._state_for_turn(session, message)
        try:
            self._save(workflow_run, state, "start", "running")

            state["active_step"] = "save_user_answer"
            answer_message = self.nodes.save_user_answer_node(state, session)
            self._save(workflow_run, state, "save_user_answer", "running")
            state["active_step"] = "load_runtime_context"
            context = self.nodes.load_runtime_context_node(state, session)
            self._save(workflow_run, state, "load_runtime_context", "running")
            state["active_step"] = "topic_judge"
            judge_result = await self.nodes.topic_judge_node(
                state=state,
                session=session,
                answer_message=answer_message,
                recent_history=context.recent_history,
                execution=context.execution,
            )
            self._save(workflow_run, state, "topic_judge", "running")
            state["active_step"] = "advance_execution"
            execution = self.nodes.advance_execution_node(
                state=state,
                execution=context.execution,
                answer_message=answer_message,
                judge_result=judge_result,
            )
            self._record_route_after_advance(state, execution)
            self._save(workflow_run, state, "advance_execution", "running")
            state["active_step"] = "refresh_memory"
            await self.nodes.refresh_memory_node(
                state=state,
                session=session,
                latest_completed_round_no=context.latest_completed_round_no,
            )
            self._save(workflow_run, state, "refresh_memory", "running")
            state["active_step"] = "reload_followup_context"
            followup_context = self.nodes.reload_followup_context_node(
                state=state,
                session=session,
                execution=execution,
            )
            self._save(workflow_run, state, "reload_followup_context", "running")
            state["active_step"] = "generate_followup"
            message_fields = await self.nodes.generate_followup_node(
                state=state,
                session=session,
                answer_message=answer_message,
                context=followup_context,
            )
            self._save(workflow_run, state, "generate_followup", "running")
            state["active_step"] = "save_assistant_message"
            assistant_message = self.nodes.save_assistant_message_node(
                state=state,
                session=session,
                round_no=answer_message.round_no + 1,
                message_fields=message_fields,
                execution=execution,
            )
            state["active_step"] = None
            self._save(workflow_run, state, "wait_user_answer", "waiting_user")
        except Exception as exc:
            self._fail(workflow_run, state, self._failed_step_id(state), exc)
            raise
        return InterviewRuntimeWorkflowResult(
            reply=assistant_message.content,
            round_no=assistant_message.round_no,
            state=state,
            answer_message_id=answer_message.id,
            assistant_message_id=assistant_message.id,
        )

    def _langgraph(self):
        if self._langgraph_runtime is None:
            from app.service.interview_runtime_langgraph import InterviewRuntimeLangGraph

            self._langgraph_runtime = InterviewRuntimeLangGraph(
                nodes=self.nodes,
                runtime=self.runtime,
                checkpointer=self.checkpointer,
                commit_after_step=self.commit_after_step,
            )
        return self._langgraph_runtime

    def _record_route_after_advance(
        self,
        state: InterviewRuntimeState,
        execution,
    ) -> str:
        decision = self.router.route_after_advance(state, execution)
        state["route_after_advance"] = decision.route
        state["route_after_advance_reason"] = decision.reason
        return decision.route

    def _state_for_turn(
        self,
        session,
        message: str,
    ) -> tuple[object | None, InterviewRuntimeState]:
        initial_state = self.nodes.initial_chat_state(
            session=session,
            incoming_user_input=message,
        )
        workflow_run = self._load_or_create_workflow_run(session, initial_state)
        if not workflow_run:
            return None, initial_state
        return (
            workflow_run,
            resume_interview_runtime_state(
                workflow_run=workflow_run,
                initial_state=initial_state,
                session=session,
                incoming_user_input=message,
            ),
        )

    def _load_or_create_workflow_run(self, session, state: InterviewRuntimeState):
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
        state: InterviewRuntimeState,
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
        self._commit_after_step()

    def _commit_after_step(self) -> None:
        if self.commit_after_step:
            self.commit_after_step()

    def _fail(
        self,
        workflow_run,
        state: InterviewRuntimeState,
        current_step: str,
        exc: Exception,
    ) -> None:
        if isinstance(exc, InterviewRuntimeWorkflowError):
            current_step = exc.step_id
        failed_steps = state.setdefault("failed_steps", [])
        if current_step not in failed_steps:
            failed_steps.append(current_step)
        state["last_error"] = {
            "step_id": current_step,
            "message": str(exc),
            "error_type": exc.__class__.__name__,
        }
        self._save(workflow_run, state, current_step, "failed")

    def _failed_step_id(self, state: InterviewRuntimeState) -> str:
        if state.get("last_error") and state["last_error"].get("step_id"):
            return state["last_error"]["step_id"]
        if state.get("active_step"):
            return state["active_step"]
        completed = state.get("completed_steps") or []
        if "generate_followup" not in completed:
            return "generate_followup"
        if "save_assistant_message" not in completed:
            return "save_assistant_message"
        return "unknown"
