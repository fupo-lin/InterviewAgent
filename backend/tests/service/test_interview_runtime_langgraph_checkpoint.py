import logging
import unittest
from types import SimpleNamespace

from service.support import configure_backend_imports

configure_backend_imports()

from app.service.interview_runtime_langgraph import InterviewRuntimeLangGraph, StateGraph
from app.service.interview_runtime_nodes import InterviewRuntimeNodes
from app.service.interview_runtime_checkpoint import create_memory_checkpointer
from app.service.interview_runtime_workflow import InterviewRuntimeWorkflow
from service.test_interview_runtime_nodes import (
    FakeAgentRunRepo,
    FakeExecutionRepo,
    FakeExecutionService,
    FakeInterviewExecutorAgent,
    FakeMessageRepo,
    FakePlanRepo,
    FakeSummaryRepo,
    FakeTopicJudgeAgent,
    FakeWorkflowRuntime,
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
        self.runtime = FakeWorkflowRuntime()
        self.checkpointer = create_memory_checkpointer()
        self.nodes = InterviewRuntimeNodes(
            message_repo=self.message_repo,
            summary_repo=FakeSummaryRepo(),
            execution_repo=FakeExecutionRepo(self.execution),
            plan_repo=FakePlanRepo(),
            execution_service=FakeExecutionService(),
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


if __name__ == "__main__":
    unittest.main()
