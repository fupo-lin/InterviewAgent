import logging
import unittest
from types import SimpleNamespace

from service.support import configure_backend_imports

configure_backend_imports()

from app.service.interview_runtime_langgraph import InterviewRuntimeLangGraph, StateGraph
from app.service.interview_runtime_router import InterviewRuntimeRouter
from app.service.interview_runtime_nodes import InterviewRuntimeNodes
from app.service.interview_runtime_checkpoint import create_memory_checkpointer
from app.service.interview_runtime_workflow import InterviewRuntimeWorkflow
from service.test_interview_runtime_nodes import (
    FakeAgentRunRepo,
    FakeExecutionRepo,
    FakeExecutionService,
    FakeInterviewExecutorAgent,
    FailingInterviewExecutorAgent,
    FakeMessageRepo,
    FakePlanRepo,
    FakeSummaryRepo,
    FakeTopicJudgeAgent,
    FakeWorkflowRuntime,
    message,
)


def memory_saver_class():
    try:
        from langgraph.checkpoint.memory import MemorySaver
    except ImportError:
        return None
    return MemorySaver


def has_memory_checkpointer_support() -> bool:
    return memory_saver_class() is not None


def latest_checkpoint(checkpointer, thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    if hasattr(checkpointer, "get_tuple"):
        return checkpointer.get_tuple(config)
    if hasattr(checkpointer, "get"):
        return checkpointer.get(config)
    return None


class FakeGraph:
    def __init__(self) -> None:
        self.calls = []

    async def ainvoke(self, state, config=None):
        self.calls.append((state, config))
        return {
            **state,
            "assistant_message_obj": SimpleNamespace(id=202, content="followup", round_no=4),
            "answer_message_obj": SimpleNamespace(id=101),
        }


class FakeInitialStateNodes:
    def initial_chat_state(self, session, incoming_user_input):
        return {
            "workflow_id": "interview_runtime",
            "thread_id": f"interview:{session.session_uid}",
            "incoming_user_input": incoming_user_input,
        }


class InterviewRuntimeLangGraphConfigTest(unittest.IsolatedAsyncioTestCase):
    async def test_resume_with_user_input_passes_stable_thread_id_config(self):
        runtime = InterviewRuntimeLangGraph.__new__(InterviewRuntimeLangGraph)
        runtime.nodes = FakeInitialStateNodes()
        runtime.runtime = None
        runtime.checkpointer = None
        runtime.graph = FakeGraph()
        session = SimpleNamespace(session_uid="session-uid")

        result = await runtime.resume_with_user_input(session, "candidate answer")

        _, config = runtime.graph.calls[0]
        self.assertEqual(
            config,
            {"configurable": {"thread_id": "interview:session-uid"}},
        )
        self.assertEqual(result.reply, "followup")
        self.assertEqual(result.answer_message_id, 101)
        self.assertEqual(result.assistant_message_id, 202)

    async def test_save_invokes_commit_after_step_hook(self):
        events = []
        runtime = InterviewRuntimeLangGraph.__new__(InterviewRuntimeLangGraph)
        runtime.runtime = FakeWorkflowRuntime()
        runtime.commit_after_step = lambda: events.append("commit")
        runtime.on_step = None
        workflow_run = runtime.runtime.load_or_create(
            workflow_id="interview_runtime",
            thread_id="interview:session-uid",
            project_id=1,
            session_id=10,
            initial_state={},
        )
        state = {
            "status": "running",
            "session_obj": object(),
            "workflow_run_obj": workflow_run,
            "completed_steps": [],
        }

        runtime._save(workflow_run, state, "save_user_answer", "running")

        self.assertEqual(events, ["commit"])
        self.assertEqual(runtime.runtime.saved[-1][1]["current_step"], "save_user_answer")
        self.assertNotIn("session_obj", runtime.runtime.saved[-1][1]["state"])

    async def test_save_invokes_on_step_hook(self):
        events = []
        runtime = InterviewRuntimeLangGraph.__new__(InterviewRuntimeLangGraph)
        runtime.runtime = FakeWorkflowRuntime()
        runtime.commit_after_step = None
        runtime.on_step = events.append
        workflow_run = runtime.runtime.load_or_create(
            workflow_id="interview_runtime",
            thread_id="interview:session-uid",
            project_id=1,
            session_id=10,
            initial_state={},
        )
        state = {
            "workflow_id": "interview_runtime",
            "workflow_run_id": "workflow-run-1",
            "thread_id": "interview:session-uid",
            "status": "running",
            "session_obj": object(),
            "workflow_run_obj": workflow_run,
            "completed_steps": ["save_user_answer"],
        }

        runtime._save(workflow_run, state, "save_user_answer", "running")

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "step")
        self.assertEqual(events[0]["step"], "save_user_answer")
        self.assertEqual(events[0]["workflowRunId"], "workflow-run-1")
        self.assertEqual(events[0]["stepMetricsSummary"]["step_count"], 0)

    async def test_save_records_active_step_metric(self):
        events = []
        runtime = InterviewRuntimeLangGraph.__new__(InterviewRuntimeLangGraph)
        runtime.runtime = FakeWorkflowRuntime()
        runtime.commit_after_step = None
        runtime.on_step = events.append
        workflow_run = runtime.runtime.load_or_create(
            workflow_id="interview_runtime",
            thread_id="interview:session-uid",
            project_id=1,
            session_id=10,
            initial_state={},
        )
        state = {
            "workflow_id": "interview_runtime",
            "workflow_run_id": "workflow-run-1",
            "thread_id": "interview:session-uid",
            "status": "running",
            "session_obj": object(),
            "workflow_run_obj": workflow_run,
            "completed_steps": ["save_user_answer"],
        }

        state["_active_step_id"] = "save_user_answer"
        state["_active_step_started_at"] = 1.0
        runtime._save(workflow_run, state, "save_user_answer", "running")

        saved_state = runtime.runtime.saved[-1][1]["state"]
        self.assertNotIn("_active_step_started_at", saved_state)
        self.assertEqual(saved_state["step_metrics"][0]["step_id"], "save_user_answer")
        self.assertEqual(saved_state["step_metrics"][0]["status"], "success")
        self.assertGreaterEqual(saved_state["step_metrics"][0]["latency_ms"], 0)
        self.assertEqual(saved_state["last_step_metric"]["step_id"], "save_user_answer")
        self.assertEqual(events[0]["stepMetricsSummary"]["step_count"], 1)

    async def test_fail_records_failed_step_metric(self):
        runtime = InterviewRuntimeLangGraph.__new__(InterviewRuntimeLangGraph)
        runtime.runtime = FakeWorkflowRuntime()
        runtime.commit_after_step = None
        runtime.on_step = None
        workflow_run = runtime.runtime.load_or_create(
            workflow_id="interview_runtime",
            thread_id="interview:session-uid",
            project_id=1,
            session_id=10,
            initial_state={},
        )
        state = {
            "workflow_id": "interview_runtime",
            "workflow_run_id": "workflow-run-1",
            "thread_id": "interview:session-uid",
            "status": "running",
            "workflow_run_obj": workflow_run,
            "completed_steps": [],
            "_active_step_id": "generate_followup",
            "_active_step_started_at": 1.0,
        }

        runtime._fail(workflow_run, state, "generate_followup", RuntimeError("boom"))

        saved_state = runtime.runtime.saved[-1][1]["state"]
        metric = saved_state["step_metrics"][0]
        self.assertEqual(metric["step_id"], "generate_followup")
        self.assertEqual(metric["status"], "failed")
        self.assertEqual(metric["error_type"], "RuntimeError")
        self.assertEqual(metric["error_message"], "boom")

    async def test_route_after_advance_execution_records_conditional_route(self):
        runtime = InterviewRuntimeLangGraph.__new__(InterviewRuntimeLangGraph)
        runtime.router = InterviewRuntimeRouter()
        state = {
            "next_action": "wrap_up_interview",
            "execution_obj": SimpleNamespace(status="active", state={}),
        }

        route = runtime._route_after_advance_execution(state)

        self.assertEqual(route, InterviewRuntimeRouter.WRAP_UP)
        self.assertEqual(state["route_after_advance"], InterviewRuntimeRouter.WRAP_UP)
        self.assertEqual(
            state["route_after_advance_reason"],
            "next_action_wrap_up_interview",
        )

    async def test_route_after_refresh_memory_splits_wrap_up_from_default(self):
        runtime = InterviewRuntimeLangGraph.__new__(InterviewRuntimeLangGraph)

        self.assertEqual(
            runtime._route_after_refresh_memory(
                {"route_after_advance": InterviewRuntimeRouter.WRAP_UP}
            ),
            InterviewRuntimeRouter.WRAP_UP,
        )
        self.assertEqual(
            runtime._route_after_refresh_memory(
                {"route_after_advance": InterviewRuntimeRouter.CONTINUE_TOPIC}
            ),
            "default",
        )


@unittest.skipIf(StateGraph is None, "langgraph is not installed")
class InterviewRuntimeLangGraphCheckpointTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        if not has_memory_checkpointer_support():
            self.skipTest("langgraph MemorySaver is not available")

        self.session = SimpleNamespace(
            id=10,
            session_uid="session-uid",
            project_id=1,
            role_name="Backend Engineer",
            interview_plan_id=20,
        )
        self.execution = SimpleNamespace(
            id=40,
            current_section_key="system_design",
            current_section_index=0,
            current_section_round_no=0,
            total_completed_round_no=0,
            state={
                "sections": [{"section_key": "system_design", "evidence": []}],
                "next_action": {"type": "continue_current_topic"},
            },
        )
        self.message_repo = FakeMessageRepo()
        self.topic_judge_agent = FakeTopicJudgeAgent()
        self.interview_executor_agent = FakeInterviewExecutorAgent()
        self.execution_service = FakeExecutionService()
        self.runtime = FakeWorkflowRuntime()
        self.checkpointer = create_memory_checkpointer()
        self.nodes = InterviewRuntimeNodes(
            message_repo=self.message_repo,
            summary_repo=FakeSummaryRepo(),
            execution_repo=FakeExecutionRepo(self.execution),
            plan_repo=FakePlanRepo(),
            execution_service=self.execution_service,
            topic_judge_agent=self.topic_judge_agent,
            session_memory_agent=None,
            interview_executor_agent=self.interview_executor_agent,
            agent_run_repo=FakeAgentRunRepo(),
            logger_=logging.getLogger("test_interview_runtime_langgraph_checkpoint"),
        )
        self.nodes.logger.disabled = True

    async def test_langgraph_runtime_writes_checkpoint_with_stable_thread_id(self):
        workflow = InterviewRuntimeWorkflow(
            self.nodes,
            runtime=self.runtime,
            use_langgraph=True,
            checkpointer=self.checkpointer,
        )

        result = await workflow.resume_with_user_input(
            session=self.session,
            message="candidate answer",
        )

        thread_id = "interview:session-uid"
        checkpoint = latest_checkpoint(self.checkpointer, thread_id)

        self.assertIsNotNone(checkpoint)
        self.assertEqual(result.reply, "followup question")
        self.assertEqual(result.state["thread_id"], thread_id)
        self.assertEqual(result.state["status"], "waiting_user")
        self.assertEqual(self.runtime.run.thread_id, thread_id)
        self.assertEqual(self.runtime.saved[-1][1]["current_step"], "wait_user_answer")
        self.assertEqual(self.runtime.saved[-1][1]["status"], "waiting_user")
        self.assertEqual(self.runtime.saved[-1][1]["state"]["status"], "waiting_user")
        self.assertEqual(self.topic_judge_agent.calls[0].workflow_run_id, "workflow-run-1")
        self.assertEqual(self.interview_executor_agent.calls[0].workflow_run_id, "workflow-run-1")

    async def test_checkpointer_does_not_hide_generate_followup_failure(self):
        self.nodes.interview_executor_agent = FailingInterviewExecutorAgent()
        workflow = InterviewRuntimeWorkflow(
            self.nodes,
            runtime=self.runtime,
            use_langgraph=True,
            checkpointer=self.checkpointer,
        )

        with self.assertRaisesRegex(RuntimeError, "followup unavailable"):
            await workflow.resume_with_user_input(
                session=self.session,
                message="candidate answer",
            )

        thread_id = "interview:session-uid"
        checkpoint = latest_checkpoint(self.checkpointer, thread_id)
        failed_save = self.runtime.saved[-1][1]

        self.assertIsNotNone(checkpoint)
        self.assertEqual(self.runtime.run.thread_id, thread_id)
        self.assertEqual(failed_save["current_step"], "generate_followup")
        self.assertEqual(failed_save["status"], "failed")
        self.assertEqual(failed_save["state"]["status"], "failed")
        self.assertEqual(failed_save["last_error"]["step_id"], "generate_followup")
        self.assertEqual(failed_save["last_error"]["message"], "followup unavailable")
        self.assertIn("generate_followup", failed_save["state"]["failed_steps"])
        self.assertNotIn("last_assistant_message_id", failed_save["state"])

    async def test_failed_retry_with_checkpointer_keeps_phase5_idempotency(self):
        existing_answer = message(999, "answer before followup failure", round_no=3)
        self.message_repo.existing_by_round[(3, "user", "answer")] = existing_answer
        self.execution.state = {
            "sections": [
                {
                    "section_key": "system_design",
                    "evidence": [{"answer_message_id": 999, "round_no": 3}],
                }
            ],
            "next_action": {"type": "continue_current_topic"},
        }
        self.runtime.run = SimpleNamespace(
            workflow_run_id="workflow-run-1",
            workflow_id="interview_runtime",
            thread_id="interview:session-uid",
            project_id=1,
            session_id=10,
            status="failed",
            current_step="generate_followup",
            state={
                "workflow_id": "interview_runtime",
                "thread_id": "interview:session-uid",
                "workflow_run_id": "workflow-run-1",
                "status": "failed",
                "incoming_user_input": "answer before followup failure",
                "last_user_message_id": 999,
                "completed_steps": ["save_user_answer", "advance_execution"],
                "failed_steps": ["generate_followup"],
                "last_error": {
                    "step_id": "generate_followup",
                    "message": "followup unavailable",
                },
            },
        )
        workflow = InterviewRuntimeWorkflow(
            self.nodes,
            runtime=self.runtime,
            use_langgraph=True,
            checkpointer=self.checkpointer,
        )

        result = await workflow.resume_with_user_input(
            session=self.session,
            message="new answer that should wait for next turn",
        )

        thread_id = "interview:session-uid"
        checkpoint = latest_checkpoint(self.checkpointer, thread_id)
        start_state = self.runtime.saved[0][1]["state"]

        self.assertIsNotNone(checkpoint)
        self.assertEqual(start_state["incoming_user_input"], "answer before followup failure")
        self.assertEqual(start_state["resume_reason"], "failed_retry")
        self.assertEqual(start_state["resume_from_step"], "generate_followup")
        self.assertEqual(start_state["failed_steps"], [])
        self.assertIsNone(start_state["last_error"])
        self.assertEqual(result.answer_message_id, 999)
        self.assertEqual(result.reply, "followup question")
        self.assertEqual(self.runtime.saved[-1][1]["current_step"], "wait_user_answer")
        self.assertEqual(self.runtime.saved[-1][1]["status"], "waiting_user")
        self.assertEqual(self.message_repo.created[0].role_type, "assistant")
        self.assertEqual(self.execution_service.advance_calls, [])
        self.assertIn("save_user_answer_reused", result.state["completed_steps"])
        self.assertIn("advance_execution_reused", result.state["completed_steps"])


if __name__ == "__main__":
    unittest.main()
