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
    def __init__(self, nodes: InterviewRuntimeNodes) -> None:
        self.nodes = nodes

    async def resume_with_user_input(
        self,
        session,
        message: str,
    ) -> InterviewRuntimeWorkflowResult:
        state = self.nodes.initial_chat_state(
            session=session,
            incoming_user_input=message,
        )
        answer_message = self.nodes.save_user_answer_node(state, session)
        context = self.nodes.load_runtime_context_node(state, session)
        judge_result = await self.nodes.topic_judge_node(
            state=state,
            session=session,
            answer_message=answer_message,
            recent_history=context.recent_history,
            execution=context.execution,
        )
        execution = self.nodes.advance_execution_node(
            state=state,
            execution=context.execution,
            answer_message=answer_message,
            judge_result=judge_result,
        )
        await self.nodes.refresh_memory_node(
            state=state,
            session=session,
            latest_completed_round_no=context.latest_completed_round_no,
        )
        followup_context = self.nodes.reload_followup_context_node(
            state=state,
            session=session,
            execution=execution,
        )
        message_fields = await self.nodes.generate_followup_node(
            state=state,
            session=session,
            answer_message=answer_message,
            context=followup_context,
        )
        assistant_message = self.nodes.save_assistant_message_node(
            state=state,
            session=session,
            round_no=answer_message.round_no + 1,
            message_fields=message_fields,
            execution=execution,
        )
        return InterviewRuntimeWorkflowResult(
            reply=assistant_message.content,
            round_no=assistant_message.round_no,
            state=state,
            answer_message_id=answer_message.id,
            assistant_message_id=assistant_message.id,
        )
