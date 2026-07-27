from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from time import perf_counter
from typing import Any, TypedDict

from app.service.interview_runtime_nodes import InterviewRuntimeNodes
from app.service.interview_runtime_decision import runtime_decision_from_route
from app.service.interview_runtime_resume import resume_interview_runtime_state
from app.service.interview_runtime_router import InterviewRuntimeRouter
from app.service.interview_runtime_state import InterviewRuntimeState
from app.service.interview_runtime_workflow import InterviewRuntimeWorkflowResult
from app.service.workflow_step_metrics import (
    record_workflow_step_metric,
    step_metrics_summary,
)


try:
    from langgraph.graph import END, START, StateGraph
except ImportError:  # pragma: no cover - exercised only when langgraph is installed
    END = None
    START = None
    StateGraph = None

# 图运行时会临时携带一些 Python 对象；这些对象只在内存中使用，不会写入 workflow_runs.state。
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


class InterviewRuntimeLangGraph:
    def __init__(
        self,
        *,
        nodes: InterviewRuntimeNodes,
        runtime=None,
        checkpointer=None,
        commit_after_step: Callable[[], None] | None = None,
        on_step: Callable[[dict], None] | None = None,
    ) -> None:
        if StateGraph is None:
            raise LangGraphNotAvailable(
                "langgraph is not installed. Install langgraph and enable "
                "USE_LANGGRAPH_INTERVIEW_RUNTIME=true to use this runtime."
            )
        self.nodes = nodes
        self.runtime = runtime
        self.checkpointer = checkpointer
        self.commit_after_step = commit_after_step
        self.on_step = on_step
        self.router = InterviewRuntimeRouter()
        self.graph = self._build_graph()

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
        # ainvoke 是 LangGraph 的异步入口：传入初始状态，返回最终状态。
        final_state = await self.graph.ainvoke(
            state,
            config={"configurable": {"thread_id": state["thread_id"]}},
        )
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

    def _build_graph(self):
        builder = StateGraph(InterviewRuntimeGraphState)
        builder.add_node("start", self._start_node)
        builder.add_node("save_user_answer", self._save_user_answer_node)
        builder.add_node("load_runtime_context", self._load_runtime_context_node)
        builder.add_node("topic_judge", self._topic_judge_node)
        builder.add_node("advance_execution", self._advance_execution_node)
        builder.add_node("refresh_memory", self._refresh_memory_node)
        builder.add_node("reload_followup_context", self._reload_followup_context_node)
        builder.add_node("reload_wrap_up_context", self._reload_wrap_up_context_node)
        builder.add_node("generate_followup", self._generate_followup_node)
        builder.add_node("generate_wrap_up_question", self._generate_wrap_up_question_node)
        builder.add_node("save_assistant_message", self._save_assistant_message_node)
        builder.add_node("save_wrap_up_message", self._save_wrap_up_message_node)
        builder.add_node("finalize_interview", self._finalize_interview_node)

        builder.add_edge(START, "start")
        builder.add_edge("start", "save_user_answer")
        builder.add_edge("save_user_answer", "load_runtime_context")
        builder.add_edge("load_runtime_context", "topic_judge")
        builder.add_edge("topic_judge", "advance_execution")
        builder.add_conditional_edges(
            "advance_execution",
            self._route_after_advance_execution,
            {
                InterviewRuntimeRouter.CONTINUE_TOPIC: "refresh_memory",
                InterviewRuntimeRouter.SWITCH_TOPIC: "refresh_memory",
                InterviewRuntimeRouter.MOVE_NEXT_SECTION: "refresh_memory",
                InterviewRuntimeRouter.WRAP_UP: "refresh_memory",
                InterviewRuntimeRouter.FINISHED: "finalize_interview",
            },
        )
        builder.add_conditional_edges(
            "refresh_memory",
            self._route_after_refresh_memory,
            {
                InterviewRuntimeRouter.WRAP_UP: "reload_wrap_up_context",
                "default": "reload_followup_context",
            },
        )
        builder.add_edge("reload_followup_context", "generate_followup")
        builder.add_edge("generate_followup", "save_assistant_message")
        builder.add_edge("save_assistant_message", END)
        builder.add_edge("reload_wrap_up_context", "generate_wrap_up_question")
        builder.add_edge("generate_wrap_up_question", "save_wrap_up_message")
        builder.add_edge("save_wrap_up_message", END)
        builder.add_edge("finalize_interview", END)
        return builder.compile(checkpointer=self.checkpointer)

    async def _start_node(self, state: InterviewRuntimeGraphState) -> dict:
        state["_active_step_id"] = "start"
        state["_active_step_started_at"] = perf_counter()
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
        self._persist_step(graph_state, "start", "running")
        return {
            **resumed_state,
            "workflow_run_obj": workflow_run,
            "session_obj": session,
        }

    async def _save_user_answer_node(self, state: InterviewRuntimeGraphState) -> dict:
        async def run() -> dict:
            answer_message = self.nodes.save_user_answer_node(state, state["session_obj"])
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
            return {
                "runtime_context_obj": context,
                "execution_id": state.get("execution_id"),
                "latest_candidate_memory_id": state.get("latest_candidate_memory_id"),
                "latest_conversation_summary_id": state.get("latest_conversation_summary_id"),
                "memory_refs": state.get("memory_refs", {}),
                "open_threads": state.get("open_threads", []),
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
            return {
                "judge_result_obj": judge_result,
                "last_topic_judge_agent_run_id": state.get("last_topic_judge_agent_run_id"),
                "last_agent_run_id": state.get("last_agent_run_id"),
                "completed_steps": state.get("completed_steps", []),
                "failed_steps": state.get("failed_steps", []),
                "last_error": state.get("last_error"),
                "open_threads": state.get("open_threads", []),
                "memory_refs": state.get("memory_refs", {}),
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
                recent_history=context.recent_history,
            )
            self._record_route_after_advance(state, execution)
            return {
                "execution_obj": execution,
                "execution_id": state.get("execution_id"),
                "current_section_key": state.get("current_section_key"),
                "current_section_index": state.get("current_section_index"),
                "current_section_round_no": state.get("current_section_round_no"),
                "total_completed_round_no": state.get("total_completed_round_no"),
                "next_action": state.get("next_action"),
                "route_after_advance": state.get("route_after_advance"),
                "route_after_advance_reason": state.get("route_after_advance_reason"),
                "runtime_decision": state.get("runtime_decision"),
                "open_threads": state.get("open_threads", []),
                "memory_refs": state.get("memory_refs", {}),
                "completed_steps": state.get("completed_steps", []),
            }

        return await self._run_node(state, "advance_execution", run)

    def _route_after_advance_execution(self, state: InterviewRuntimeGraphState) -> str:
        route = state.get("route_after_advance")
        if isinstance(route, str) and route:
            return route
        return self._record_route_after_advance(
            state,
            state.get("execution_obj"),
        )

    def _record_route_after_advance(
        self,
        state: InterviewRuntimeGraphState,
        execution,
    ) -> str:
        decision = self.router.route_after_advance(state, execution)
        state["route_after_advance"] = decision.route
        state["route_after_advance_reason"] = decision.reason
        runtime_decision_from_route(
            state=state,
            execution=execution,
            route_decision=decision,
        )
        return decision.route

    def _route_after_refresh_memory(self, state: InterviewRuntimeGraphState) -> str:
        if state.get("route_after_advance") == InterviewRuntimeRouter.WRAP_UP:
            return InterviewRuntimeRouter.WRAP_UP
        return "default"

    async def _refresh_memory_node(self, state: InterviewRuntimeGraphState) -> dict:
        async def run() -> dict:
            context = state["runtime_context_obj"]
            await self.nodes.refresh_memory_node(
                state=state,
                session=state["session_obj"],
                latest_completed_round_no=context.latest_completed_round_no,
            )
            return {
                "latest_candidate_memory_id": state.get("latest_candidate_memory_id"),
                "latest_conversation_summary_id": state.get("latest_conversation_summary_id"),
                "last_memory_agent_run_ids": state.get("last_memory_agent_run_ids", []),
                "memory_refs": state.get("memory_refs", {}),
                "open_threads": state.get("open_threads", []),
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
            return {
                "followup_context_obj": context,
                "latest_candidate_memory_id": state.get("latest_candidate_memory_id"),
                "latest_conversation_summary_id": state.get("latest_conversation_summary_id"),
                "memory_refs": state.get("memory_refs", {}),
                "open_threads": state.get("open_threads", []),
                "completed_steps": state.get("completed_steps", []),
            }

        return await self._run_node(state, "reload_followup_context", run)

    async def _reload_wrap_up_context_node(self, state: InterviewRuntimeGraphState) -> dict:
        async def run() -> dict:
            context = self.nodes.build_runtime_context(
                state=state,
                session=state["session_obj"],
                execution=state.get("execution_obj"),
                completed_step_id="reload_wrap_up_context",
            )
            return {
                "followup_context_obj": context,
                "latest_candidate_memory_id": state.get("latest_candidate_memory_id"),
                "latest_conversation_summary_id": state.get("latest_conversation_summary_id"),
                "memory_refs": state.get("memory_refs", {}),
                "open_threads": state.get("open_threads", []),
                "completed_steps": state.get("completed_steps", []),
            }

        return await self._run_node(state, "reload_wrap_up_context", run)

    async def _generate_followup_node(self, state: InterviewRuntimeGraphState) -> dict:
        async def run() -> dict:
            message_fields = await self.nodes.generate_followup_node(
                state=state,
                session=state["session_obj"],
                answer_message=state["answer_message_obj"],
                context=state["followup_context_obj"],
            )
            return {
                "message_fields_obj": message_fields,
                "last_followup_agent_run_id": state.get("last_followup_agent_run_id"),
                "last_agent_run_id": state.get("last_agent_run_id"),
                "memory_refs": state.get("memory_refs", {}),
                "open_threads": state.get("open_threads", []),
                "completed_steps": state.get("completed_steps", []),
            }

        return await self._run_node(state, "generate_followup", run)

    async def _generate_wrap_up_question_node(self, state: InterviewRuntimeGraphState) -> dict:
        async def run() -> dict:
            message_fields = await self.nodes.generate_wrap_up_question_node(
                state=state,
                session=state["session_obj"],
                answer_message=state["answer_message_obj"],
                context=state["followup_context_obj"],
            )
            return {
                "message_fields_obj": message_fields,
                "last_followup_agent_run_id": state.get("last_followup_agent_run_id"),
                "last_agent_run_id": state.get("last_agent_run_id"),
                "memory_refs": state.get("memory_refs", {}),
                "open_threads": state.get("open_threads", []),
                "completed_steps": state.get("completed_steps", []),
            }

        return await self._run_node(state, "generate_wrap_up_question", run)

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
            return {
                "assistant_message_obj": assistant_message,
                "last_assistant_message_id": assistant_message.id,
                "status": state.get("status"),
                "active_step": None,
                "open_threads": state.get("open_threads", []),
                "memory_refs": state.get("memory_refs", {}),
                "completed_steps": state.get("completed_steps", []),
            }

        return await self._run_node(state, "save_assistant_message", run)

    async def _save_wrap_up_message_node(self, state: InterviewRuntimeGraphState) -> dict:
        async def run() -> dict:
            answer_message = state["answer_message_obj"]
            assistant_message = self.nodes.save_wrap_up_message_node(
                state=state,
                session=state["session_obj"],
                round_no=answer_message.round_no + 1,
                message_fields=state["message_fields_obj"],
                execution=state.get("execution_obj"),
            )
            state["active_step"] = None
            return {
                "assistant_message_obj": assistant_message,
                "last_assistant_message_id": assistant_message.id,
                "status": state.get("status"),
                "active_step": None,
                "open_threads": state.get("open_threads", []),
                "memory_refs": state.get("memory_refs", {}),
                "completed_steps": state.get("completed_steps", []),
            }

        return await self._run_node(state, "save_wrap_up_message", run)

    async def _finalize_interview_node(self, state: InterviewRuntimeGraphState) -> dict:
        async def run() -> dict:
            assistant_message = self.nodes.finalize_interview_node(
                state=state,
                session=state["session_obj"],
                answer_message=state["answer_message_obj"],
                execution=state.get("execution_obj"),
            )
            return {
                "assistant_message_obj": assistant_message,
                "last_assistant_message_id": assistant_message.id,
                "status": state.get("status"),
                "active_step": None,
                "open_threads": state.get("open_threads", []),
                "memory_refs": state.get("memory_refs", {}),
                "completed_steps": state.get("completed_steps", []),
            }

        return await self._run_node(state, "finalize_interview", run)

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
        state["_active_step_id"] = step_id
        state["_active_step_started_at"] = perf_counter()
        try:
            result = await run()
            persist_step, persist_status = self._persist_target_for_step(step_id)
            result = {**result, "status": persist_status}
            if persist_step == "wait_user_answer":
                state["active_step"] = None
                result = {**result, "active_step": None}
            state.update(result)
            self._persist_step(state, persist_step, persist_status)
            return result
        except Exception as exc:
            self._fail(state.get("workflow_run_obj"), state, step_id, exc)
            raise

    def _persist_target_for_step(self, step_id: str) -> tuple[str, str]:
        if step_id in {"save_assistant_message", "save_wrap_up_message"}:
            return "wait_user_answer", "waiting_user"
        if step_id == "finalize_interview":
            return "complete", "finished"
        return step_id, "running"

    def _save(
        self,
        workflow_run,
        state: InterviewRuntimeGraphState,
        current_step: str,
        status: str,
    ) -> None:
        if workflow_run is not None:
            state["workflow_run_obj"] = workflow_run
        self._persist_step(state, current_step, status)

    def _persist_step(
        self,
        state: InterviewRuntimeGraphState,
        current_step: str,
        status: str,
    ) -> None:
        workflow_run = state.get("workflow_run_obj")
        if not self.runtime or not workflow_run:
            return
        state["status"] = status
        self._record_active_step_metric(
            state=state,
            current_step=current_step,
            status=status,
        )
        self.runtime.save(
            workflow_run,
            state=deepcopy(self._public_state(state)),
            current_step=current_step,
            status=status,
            last_error=state.get("last_error"),
        )
        self._emit_step(state, current_step, status)
        self._commit_after_step()

    def _commit_after_step(self) -> None:
        if self.commit_after_step:
            self.commit_after_step()

    def _emit_step(
        self,
        state: InterviewRuntimeGraphState,
        current_step: str,
        status: str,
    ) -> None:
        if not self.on_step:
            return
        public_state = self._public_state(state)
        self.on_step(
            {
                "event": "step",
                "workflowRunId": public_state.get("workflow_run_id"),
                "workflowId": public_state.get("workflow_id"),
                "threadId": public_state.get("thread_id"),
                "step": current_step,
                "status": status,
                "activeStep": public_state.get("active_step"),
                "routeAfterAdvance": public_state.get("route_after_advance"),
                "routeAfterAdvanceReason": public_state.get("route_after_advance_reason"),
                "runtimeDecision": public_state.get("runtime_decision"),
                "openThreads": public_state.get("open_threads") or [],
                "memoryRefs": public_state.get("memory_refs") or {},
                "stepMetricsSummary": step_metrics_summary(public_state),
                "completedSteps": public_state.get("completed_steps") or [],
                "failedSteps": public_state.get("failed_steps") or [],
                "lastError": public_state.get("last_error"),
            }
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

    def _record_active_step_metric(
        self,
        *,
        state: InterviewRuntimeGraphState,
        current_step: str,
        status: str,
    ) -> None:
        step_id = state.get("_active_step_id")
        started = state.get("_active_step_started_at")
        if not step_id or started is None:
            return
        latency_ms = int((perf_counter() - float(started)) * 1000)
        metric_status = "failed" if status == "failed" else "success"
        record_workflow_step_metric(
            state,
            step_id=str(step_id),
            status=metric_status,
            latency_ms=latency_ms,
            current_step=current_step,
            last_error=state.get("last_error"),
        )
        state.pop("_active_step_id", None)
        state.pop("_active_step_started_at", None)

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
            "_active_step_id",
            "_active_step_started_at",
        }
        return {
            key: value
            for key, value in state.items()
            if key not in private_keys
        }
