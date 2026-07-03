from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from app.config.settings import settings
from app.service.interview_runtime_nodes import InterviewRuntimeNodes
from app.service.interview_runtime_resume import resume_interview_runtime_state
from app.service.interview_runtime_state import InterviewRuntimeState


@dataclass(frozen=True)
class InterviewRuntimeWorkflowResult:
    reply: str
    round_no: int
    state: InterviewRuntimeState
    answer_message_id: int
    assistant_message_id: int


class InterviewRuntimeWorkflow:
    def __init__(
        self,
        nodes: InterviewRuntimeNodes,
        runtime=None,
        use_langgraph: bool | None = None,
    ) -> None:
        self.nodes = nodes
        self.runtime = runtime
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
        self._save(workflow_run, state, "start", "running")

        answer_message = self.nodes.save_user_answer_node(state, session)
        self._save(workflow_run, state, "save_user_answer", "running")
        context = self.nodes.load_runtime_context_node(state, session)
        self._save(workflow_run, state, "load_runtime_context", "running")
        judge_result = await self.nodes.topic_judge_node(
            state=state,
            session=session,
            answer_message=answer_message,
            recent_history=context.recent_history,
            execution=context.execution,
        )
        self._save(workflow_run, state, "topic_judge", "running")
        execution = self.nodes.advance_execution_node(
            state=state,
            execution=context.execution,
            answer_message=answer_message,
            judge_result=judge_result,
        )
        self._save(workflow_run, state, "advance_execution", "running")
        await self.nodes.refresh_memory_node(
            state=state,
            session=session,
            latest_completed_round_no=context.latest_completed_round_no,
        )
        self._save(workflow_run, state, "refresh_memory", "running")
        followup_context = self.nodes.reload_followup_context_node(
            state=state,
            session=session,
            execution=execution,
        )
        self._save(workflow_run, state, "reload_followup_context", "running")
        message_fields = await self.nodes.generate_followup_node(
            state=state,
            session=session,
            answer_message=answer_message,
            context=followup_context,
        )
        self._save(workflow_run, state, "generate_followup", "running")
        assistant_message = self.nodes.save_assistant_message_node(
            state=state,
            session=session,
            round_no=answer_message.round_no + 1,
            message_fields=message_fields,
            execution=execution,
        )
        self._save(workflow_run, state, "wait_user_answer", "waiting_user")
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
            )
        return self._langgraph_runtime

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
