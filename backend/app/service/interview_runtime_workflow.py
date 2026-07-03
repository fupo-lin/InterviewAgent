from __future__ import annotations

from dataclasses import dataclass

from app.service.interview_runtime_nodes import InterviewRuntimeNodes
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
    ) -> None:
        self.nodes = nodes
        self.runtime = runtime

    async def resume_with_user_input(
        self,
        session,
        message: str,
    ) -> InterviewRuntimeWorkflowResult:
        state = self.nodes.initial_chat_state(
            session=session,
            incoming_user_input=message,
        )
        workflow_run = self._load_or_create_workflow_run(session, state)
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

    def _load_or_create_workflow_run(self, session, state: InterviewRuntimeState):
        if not self.runtime:
            return None
        workflow_run = self.runtime.load_or_create(
            workflow_id=state["workflow_id"],
            thread_id=state["thread_id"],
            project_id=session.project_id,
            session_id=session.id,
            initial_state=state,
        )
        state["workflow_run_id"] = workflow_run.workflow_run_id
        stored_state = workflow_run.state or {}
        if stored_state:
            state.setdefault("completed_steps", stored_state.get("completed_steps", []))
            state.setdefault("failed_steps", stored_state.get("failed_steps", []))
        return workflow_run

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
            state=dict(state),
            current_step=current_step,
            status=status,
            last_error=state.get("last_error"),
        )
