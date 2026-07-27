from __future__ import annotations

from collections.abc import Callable
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
        on_step: Callable[[dict], None] | None = None,
    ) -> None:
        if use_langgraph is False:
            raise ValueError(
                "InterviewRuntimeWorkflow is LangGraph-only. "
                "Sequential interview runtime has been removed."
            )
        self.nodes = nodes
        self.runtime = runtime
        self.checkpointer = checkpointer
        self.commit_after_step = commit_after_step
        self.on_step = on_step
        self._langgraph_runtime = None

    async def resume_with_user_input(
        self,
        session,
        message: str,
    ) -> InterviewRuntimeWorkflowResult:
        return await self._langgraph().resume_with_user_input(session, message)

    def _langgraph(self):
        if self._langgraph_runtime is None:
            from app.service.interview_runtime_langgraph import InterviewRuntimeLangGraph

            self._langgraph_runtime = InterviewRuntimeLangGraph(
                nodes=self.nodes,
                runtime=self.runtime,
                checkpointer=self.checkpointer,
                commit_after_step=self.commit_after_step,
                on_step=self.on_step,
            )
        return self._langgraph_runtime
