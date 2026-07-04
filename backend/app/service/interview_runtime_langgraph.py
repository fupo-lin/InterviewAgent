from __future__ import annotations

from copy import deepcopy
from typing import Any, TypedDict

from app.service.interview_runtime_nodes import InterviewRuntimeNodes
from app.service.interview_runtime_resume import resume_interview_runtime_state
from app.service.interview_runtime_state import InterviewRuntimeState
from app.service.interview_runtime_workflow import InterviewRuntimeWorkflowResult


try:
    from langgraph.graph import END, START, StateGraph
except ImportError:  # pragma: no cover - exercised only when langgraph is installed
    END = None
    START = None
    StateGraph = None

# 定义图的状态，继承了 InterviewRuntimeState，并添加了额外的属性，total=False表示这些属性是可选的
class InterviewRuntimeGraphState(InterviewRuntimeState, total=False):
    session_obj: Any
    workflow_run_obj: Any
    answer_message_obj: Any
    runtime_context_obj: Any
    judge_result_obj: Any
    execution_obj: Any
    followup_context_obj: Any
    message_fields_obj: dict
    assistant_message_obj: Any


class LangGraphNotAvailable(RuntimeError):
    pass

# 初始化的时候会直接调用 _build_graph 方法来构建图的结构
class InterviewRuntimeLangGraph:
    def __init__(
        self,
        *,
        nodes: InterviewRuntimeNodes,
        runtime=None,
    ) -> None:
        if StateGraph is None:
            raise LangGraphNotAvailable(
                "langgraph is not installed. Install langgraph and enable "
                "USE_LANGGRAPH_INTERVIEW_RUNTIME=true to use this runtime."
            )
        self.nodes = nodes
        self.runtime = runtime
        self.graph = self._build_graph()

# 入口方法 -- 外部调用的接口
    async def resume_with_user_input(
        self,
        session,
        message: str,
    ) -> InterviewRuntimeWorkflowResult:
        state: InterviewRuntimeGraphState = {
            **self.nodes.initial_chat_state(
                session=session,
                incoming_user_input=message,
            ),
            "session_obj": session,
        }
        final_state = await self.graph.ainvoke(state) # ainvoke是异步调用图的入口方法，传入初始状态，返回最终状态
        assistant_message = final_state["assistant_message_obj"]
        answer_message = final_state["answer_message_obj"]
        public_state = self._public_state(final_state)
        return InterviewRuntimeWorkflowResult(
            reply=assistant_message.content,
            round_no=assistant_message.round_no,
            state=public_state,
            answer_message_id=answer_message.id,
            assistant_message_id=assistant_message.id,
        )

# 构建图的结构，这是面试Runtime的标准作业程序
    def _build_graph(self):
        builder = StateGraph(InterviewRuntimeGraphState)
        builder.add_node("start", self._start_node)
        builder.add_node("save_user_answer", self._save_user_answer_node)
        builder.add_node("load_runtime_context", self._load_runtime_context_node)
        builder.add_node("topic_judge", self._topic_judge_node)
        builder.add_node("advance_execution", self._advance_execution_node)
        builder.add_node("refresh_memory", self._refresh_memory_node)
        builder.add_node("reload_followup_context", self._reload_followup_context_node)
        builder.add_node("generate_followup", self._generate_followup_node)
        builder.add_node("save_assistant_message", self._save_assistant_message_node)

        builder.add_edge(START, "start")
        builder.add_edge("start", "save_user_answer")
        builder.add_edge("save_user_answer", "load_runtime_context")
        builder.add_edge("load_runtime_context", "topic_judge")
        builder.add_edge("topic_judge", "advance_execution")
        builder.add_edge("advance_execution", "refresh_memory")
        builder.add_edge("refresh_memory", "reload_followup_context")
        builder.add_edge("reload_followup_context", "generate_followup")
        builder.add_edge("generate_followup", "save_assistant_message")
        builder.add_edge("save_assistant_message", END)
        return builder.compile()

    async def _start_node(self, state: InterviewRuntimeGraphState) -> dict:
        session = state["session_obj"]
        initial_state = self._public_state(state)
        workflow_run = self._load_or_create_workflow_run(session, initial_state)
        if workflow_run:
            resumed_state = resume_interview_runtime_state(
                workflow_run=workflow_run,
                initial_state=initial_state,
                session=session,
                incoming_user_input=state.get("incoming_user_input") or "",
            )
        else:
            resumed_state = initial_state
        graph_state = {
            **state,
            **resumed_state,
            "workflow_run_obj": workflow_run,
        }
        self._save(workflow_run, graph_state, "start", "running")
        return {
            **resumed_state,
            "workflow_run_obj": workflow_run,
            "session_obj": session,
        }

    async def _save_user_answer_node(self, state: InterviewRuntimeGraphState) -> dict:
        async def run() -> dict:
            answer_message = self.nodes.save_user_answer_node(state, state["session_obj"])
            self._save(state.get("workflow_run_obj"), state, "save_user_answer", "running")
            return {
                "answer_message_obj": answer_message,
                "last_user_message_id": answer_message.id,
                "expected_user_round_no": state.get("expected_user_round_no"),
                "completed_steps": state.get("completed_steps", []),
            }

        return await self._run_node(state, "save_user_answer", run)

    async def _load_runtime_context_node(self, state: InterviewRuntimeGraphState) -> dict:
        async def run() -> dict:
            context = self.nodes.load_runtime_context_node(state, state["session_obj"])
            self._save(state.get("workflow_run_obj"), state, "load_runtime_context", "running")
            return {
                "runtime_context_obj": context,
                "execution_id": state.get("execution_id"),
                "latest_candidate_memory_id": state.get("latest_candidate_memory_id"),
                "latest_conversation_summary_id": state.get("latest_conversation_summary_id"),
                "completed_steps": state.get("completed_steps", []),
            }

        return await self._run_node(state, "load_runtime_context", run)

    async def _topic_judge_node(self, state: InterviewRuntimeGraphState) -> dict:
        async def run() -> dict:
            context = state["runtime_context_obj"]
            judge_result = await self.nodes.topic_judge_node(
                state=state,
                session=state["session_obj"],
                answer_message=state["answer_message_obj"],
                recent_history=context.recent_history,
                execution=context.execution,
            )
            self._save(state.get("workflow_run_obj"), state, "topic_judge", "running")
            return {
                "judge_result_obj": judge_result,
                "last_topic_judge_agent_run_id": state.get("last_topic_judge_agent_run_id"),
                "last_agent_run_id": state.get("last_agent_run_id"),
                "completed_steps": state.get("completed_steps", []),
                "failed_steps": state.get("failed_steps", []),
                "last_error": state.get("last_error"),
            }

        return await self._run_node(state, "topic_judge", run)

    async def _advance_execution_node(self, state: InterviewRuntimeGraphState) -> dict:
        async def run() -> dict:
            context = state["runtime_context_obj"]
            execution = self.nodes.advance_execution_node(
                state=state,
                execution=context.execution,
                answer_message=state["answer_message_obj"],
                judge_result=state.get("judge_result_obj"),
            )
            self._save(state.get("workflow_run_obj"), state, "advance_execution", "running")
            return {
                "execution_obj": execution,
                "execution_id": state.get("execution_id"),
                "current_section_key": state.get("current_section_key"),
                "current_section_index": state.get("current_section_index"),
                "current_section_round_no": state.get("current_section_round_no"),
                "total_completed_round_no": state.get("total_completed_round_no"),
                "next_action": state.get("next_action"),
                "completed_steps": state.get("completed_steps", []),
            }

        return await self._run_node(state, "advance_execution", run)

    async def _refresh_memory_node(self, state: InterviewRuntimeGraphState) -> dict:
        async def run() -> dict:
            context = state["runtime_context_obj"]
            await self.nodes.refresh_memory_node(
                state=state,
                session=state["session_obj"],
                latest_completed_round_no=context.latest_completed_round_no,
            )
            self._save(state.get("workflow_run_obj"), state, "refresh_memory", "running")
            return {
                "latest_candidate_memory_id": state.get("latest_candidate_memory_id"),
                "latest_conversation_summary_id": state.get("latest_conversation_summary_id"),
                "last_memory_agent_run_ids": state.get("last_memory_agent_run_ids", []),
                "completed_steps": state.get("completed_steps", []),
                "failed_steps": state.get("failed_steps", []),
                "last_error": state.get("last_error"),
            }

        return await self._run_node(state, "refresh_memory", run)

    async def _reload_followup_context_node(self, state: InterviewRuntimeGraphState) -> dict:
        async def run() -> dict:
            context = self.nodes.reload_followup_context_node(
                state=state,
                session=state["session_obj"],
                execution=state.get("execution_obj"),
            )
            self._save(state.get("workflow_run_obj"), state, "reload_followup_context", "running")
            return {
                "followup_context_obj": context,
                "latest_candidate_memory_id": state.get("latest_candidate_memory_id"),
                "latest_conversation_summary_id": state.get("latest_conversation_summary_id"),
                "completed_steps": state.get("completed_steps", []),
            }

        return await self._run_node(state, "reload_followup_context", run)

    async def _generate_followup_node(self, state: InterviewRuntimeGraphState) -> dict:
        async def run() -> dict:
            message_fields = await self.nodes.generate_followup_node(
                state=state,
                session=state["session_obj"],
                answer_message=state["answer_message_obj"],
                context=state["followup_context_obj"],
            )
            self._save(state.get("workflow_run_obj"), state, "generate_followup", "running")
            return {
                "message_fields_obj": message_fields,
                "last_followup_agent_run_id": state.get("last_followup_agent_run_id"),
                "last_agent_run_id": state.get("last_agent_run_id"),
                "completed_steps": state.get("completed_steps", []),
            }

        return await self._run_node(state, "generate_followup", run)

    async def _save_assistant_message_node(self, state: InterviewRuntimeGraphState) -> dict:
        async def run() -> dict:
            answer_message = state["answer_message_obj"]
            assistant_message = self.nodes.save_assistant_message_node(
                state=state,
                session=state["session_obj"],
                round_no=answer_message.round_no + 1,
                message_fields=state["message_fields_obj"],
                execution=state.get("execution_obj"),
            )
            state["active_step"] = None
            self._save(state.get("workflow_run_obj"), state, "wait_user_answer", "waiting_user")
            return {
                "assistant_message_obj": assistant_message,
                "last_assistant_message_id": assistant_message.id,
                "status": state.get("status"),
                "active_step": None,
                "completed_steps": state.get("completed_steps", []),
            }

        return await self._run_node(state, "save_assistant_message", run)

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

    async def _run_node(
        self,
        state: InterviewRuntimeGraphState,
        step_id: str,
        run,
    ) -> dict:
        state["active_step"] = step_id
        try:
            return await run()
        except Exception as exc:
            self._fail(state.get("workflow_run_obj"), state, step_id, exc)
            raise

    def _save(
        self,
        workflow_run,
        state: InterviewRuntimeGraphState,
        current_step: str,
        status: str,
    ) -> None:
        if not self.runtime or not workflow_run:
            return
        state["status"] = status
        self.runtime.save(
            workflow_run,
            state=deepcopy(self._public_state(state)),
            current_step=current_step,
            status=status,
            last_error=state.get("last_error"),
        )

    def _fail(
        self,
        workflow_run,
        state: InterviewRuntimeGraphState,
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

    def _public_state(self, state: InterviewRuntimeGraphState) -> InterviewRuntimeState:
        private_keys = {
            "session_obj",
            "workflow_run_obj",
            "answer_message_obj",
            "runtime_context_obj",
            "judge_result_obj",
            "execution_obj",
            "followup_context_obj",
            "message_fields_obj",
            "assistant_message_obj",
        }
        return {
            key: value
            for key, value in state.items()
            if key not in private_keys
        }
