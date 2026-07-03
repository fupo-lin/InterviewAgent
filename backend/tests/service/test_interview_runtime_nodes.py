import unittest
import logging
from types import SimpleNamespace

from service.support import configure_backend_imports

configure_backend_imports()

from app.service.interview_runtime_nodes import InterviewRuntimeNodes
from app.service.interview_runtime_workflow import InterviewRuntimeWorkflow


def message(
    message_id: int,
    content: str,
    role_type: str = "user",
    message_type: str = "answer",
    round_no: int = 1,
):
    return SimpleNamespace(
        id=message_id,
        session_id=10,
        role_type=role_type,
        message_type=message_type,
        round_no=round_no,
        content=content,
        raw_response=None,
        agent_run_id=None,
        schema_version=None,
        evidence_refs=[],
    )


class FakeMessageRepo:
    def __init__(self) -> None:
        self.created = []
        self.latest_completed = 0
        self.existing_by_round = {}

    def latest_assistant_question_round_no(self, session_id):
        return 3

    def latest_completed_round_no(self, session_id):
        return self.latest_completed

    def list_recent_rounds(self, session_id, rounds):
        return [message(30, "previous answer", round_no=2)]

    def list_between_rounds(self, session_id, from_round_no, to_round_no):
        return []

    def get_by_round(self, session_id, round_no, role_type, message_type=None):
        return self.existing_by_round.get((round_no, role_type, message_type))

    def create(self, **kwargs):
        created = message(
            100 + len(self.created),
            kwargs["content"],
            role_type=kwargs["role_type"],
            message_type=kwargs["message_type"],
            round_no=kwargs["round_no"],
        )
        created.raw_response = kwargs.get("raw_response")
        created.agent_run_id = kwargs.get("agent_run_id")
        created.schema_version = kwargs.get("schema_version")
        created.evidence_refs = kwargs.get("evidence_refs") or []
        self.created.append(created)
        if created.role_type == "user":
            self.latest_completed = created.round_no
        return created


class FakeSummaryRepo:
    def get_latest_by_session_id(self, session_id, summary_type):
        return None


class FakeExecutionRepo:
    def __init__(self, execution=None) -> None:
        self.execution = execution
        self.save_calls = []

    def get_active_by_session_id(self, session_id):
        return self.execution

    def get_latest_by_session_id(self, session_id):
        return self.execution

    def save(self, execution):
        self.save_calls.append(execution)
        return execution


class FakePlanRepo:
    def get_by_id(self, plan_id):
        return SimpleNamespace(
            id=plan_id,
            plan_mode="jd_resume",
            content={
                "role_name": "Backend Engineer",
                "sections": [{"section_key": "system_design"}],
            },
        )


class FakeAgentRunRepo:
    def __init__(self) -> None:
        self.runs = {}

    def get_latest_success_by_context(self, session_id, prompt_id, context_refs, limit=50):
        key = (
            session_id,
            prompt_id,
            tuple(sorted(context_refs.items())),
        )
        return self.runs.get(key)


class FakeExecutionService:
    def __init__(self) -> None:
        self.advance_calls = []

    def current_section(self, execution):
        return {"section_key": "system_design", "probe_points": ["idempotency"]}

    def advance_after_answer(self, execution, answer, round_no, judge_result=None):
        self.advance_calls.append((answer, round_no, judge_result))
        sections = (execution.state or {}).get("sections") or []
        if sections:
            evidence = sections[0].setdefault("evidence", [])
            evidence.append({"round_no": round_no, "answer_excerpt": answer})
        execution.current_section_round_no += 1
        execution.total_completed_round_no += 1
        execution.state = {
            **(execution.state or {}),
            "next_action": {"type": "continue_current_topic"},
        }
        return execution

    def context_for_followup(self, execution, plan_content=None):
        return "execution context"

    def response(self, execution):
        return {"nextAction": "continue_current_topic"}


class FakeTopicJudgeAgent:
    def __init__(self) -> None:
        self.calls = []

    async def run(self, agent_input):
        self.calls.append(agent_input)
        return SimpleNamespace(
            output={"next_action": "continue_current_topic", "answer_quality": "high"},
            raw_response={"raw": "judge"},
            agent_run=SimpleNamespace(id=501),
            output_schema="TopicJudgeResult.v1",
            evidence_refs=["interview_answer_100"],
        )


class FailingTopicJudgeAgent:
    async def run(self, agent_input):
        raise RuntimeError("judge unavailable")


class FakeSessionMemoryAgent:
    async def run(self, agent_input):
        raise AssertionError("memory should be skipped in this test")


class FakeInterviewExecutorAgent:
    def __init__(self) -> None:
        self.calls = []

    async def run(self, agent_input):
        self.calls.append(agent_input)
        return SimpleNamespace(
            agent_run=SimpleNamespace(id=601),
            message_fields=lambda: {
                "content": "followup question",
                "raw_response": {"raw": "followup"},
                "agent_run_id": 601,
                "schema_version": "InterviewQuestion.v1",
                "evidence_refs": ["interview_answer_100"],
            },
        )


class InterviewRuntimeNodesTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
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
            state={"next_action": {"type": "continue_current_topic"}},
        )
        self.message_repo = FakeMessageRepo()
        self.execution_service = FakeExecutionService()
        self.agent_run_repo = FakeAgentRunRepo()
        self.topic_judge_agent = FakeTopicJudgeAgent()
        self.interview_executor_agent = FakeInterviewExecutorAgent()
        self.nodes = InterviewRuntimeNodes(
            message_repo=self.message_repo,
            summary_repo=FakeSummaryRepo(),
            execution_repo=FakeExecutionRepo(self.execution),
            plan_repo=FakePlanRepo(),
            execution_service=self.execution_service,
            topic_judge_agent=self.topic_judge_agent,
            session_memory_agent=FakeSessionMemoryAgent(),
            interview_executor_agent=self.interview_executor_agent,
            agent_run_repo=self.agent_run_repo,
            logger_=logging.getLogger("test_interview_runtime_nodes"),
        )
        self.nodes.logger.disabled = True

    async def test_chat_nodes_preserve_runtime_flow(self):
        state = self.nodes.initial_chat_state(self.session, "candidate answer")
        self.execution.state = {
            "sections": [
                {
                    "section_key": "system_design",
                    "evidence": [],
                }
            ],
            "next_action": {"type": "continue_current_topic"},
        }

        answer = self.nodes.save_user_answer_node(state, self.session)
        context = self.nodes.load_runtime_context_node(state, self.session)
        judge_result = await self.nodes.topic_judge_node(
            state,
            self.session,
            answer,
            context.recent_history,
            context.execution,
        )
        execution = self.nodes.advance_execution_node(
            state,
            context.execution,
            answer,
            judge_result,
        )
        await self.nodes.refresh_memory_node(
            state,
            self.session,
            context.latest_completed_round_no,
        )
        followup_context = self.nodes.reload_followup_context_node(
            state,
            self.session,
            execution,
        )
        fields = await self.nodes.generate_followup_node(
            state,
            self.session,
            answer,
            followup_context,
        )
        assistant = self.nodes.save_assistant_message_node(
            state,
            self.session,
            answer.round_no + 1,
            fields,
            execution,
        )

        self.assertEqual(answer.content, "candidate answer")
        self.assertEqual(answer.round_no, 3)
        self.assertEqual(judge_result["agent_run_id"], 501)
        self.assertEqual(self.execution_service.advance_calls[0][0], "candidate answer")
        self.assertEqual(
            self.execution.state["sections"][0]["evidence"][-1]["answer_message_id"],
            answer.id,
        )
        self.assertEqual(
            self.execution.state["sections"][0]["evidence"][-1]["topic_judge_agent_run_id"],
            501,
        )
        self.assertEqual(len(self.nodes.execution_repo.save_calls), 1)
        self.assertEqual(fields["content"], "followup question")
        self.assertEqual(assistant.content, "followup question")
        self.assertEqual(assistant.round_no, 4)
        self.assertEqual(state["last_topic_judge_agent_run_id"], 501)
        self.assertEqual(state["last_followup_agent_run_id"], 601)
        self.assertEqual(state["status"], "waiting_user")
        self.assertIn("save_user_answer", state["completed_steps"])
        self.assertIn("save_assistant_message", state["completed_steps"])
        self.assertEqual(len(self.message_repo.created), 2)

    async def test_topic_judge_failure_is_non_blocking(self):
        self.nodes.topic_judge_agent = FailingTopicJudgeAgent()
        state = self.nodes.initial_chat_state(self.session, "candidate answer")
        answer = self.nodes.save_user_answer_node(state, self.session)
        context = self.nodes.load_runtime_context_node(state, self.session)

        judge_result = await self.nodes.topic_judge_node(
            state,
            self.session,
            answer,
            context.recent_history,
            context.execution,
        )

        self.assertIsNone(judge_result)
        self.assertIn("topic_judge", state["failed_steps"])
        self.assertEqual(state["last_error"]["step_id"], "topic_judge")

    async def test_save_user_answer_reuses_existing_round_message(self):
        existing = message(999, "existing answer", round_no=3)
        self.message_repo.existing_by_round[(3, "user", "answer")] = existing
        state = self.nodes.initial_chat_state(self.session, "new answer")

        answer = self.nodes.save_user_answer_node(state, self.session)

        self.assertIs(answer, existing)
        self.assertEqual(state["last_user_message_id"], 999)
        self.assertIn("save_user_answer_reused", state["completed_steps"])
        self.assertEqual(self.message_repo.created, [])

    async def test_save_assistant_message_reuses_existing_round_message(self):
        existing = message(
            998,
            "existing followup",
            role_type="assistant",
            message_type="followup",
            round_no=4,
        )
        self.message_repo.existing_by_round[(4, "assistant", None)] = existing
        state = self.nodes.initial_chat_state(self.session, "candidate answer")

        assistant = self.nodes.save_assistant_message_node(
            state,
            self.session,
            4,
            {"content": "new followup", "raw_response": None},
            self.execution,
        )

        self.assertIs(assistant, existing)
        self.assertEqual(state["last_assistant_message_id"], 998)
        self.assertEqual(state["status"], "waiting_user")
        self.assertIn("save_assistant_message_reused", state["completed_steps"])
        self.assertEqual(self.message_repo.created, [])

    async def test_advance_execution_reuses_existing_answer_marker(self):
        answer = message(777, "candidate answer", round_no=3)
        self.execution.state = {
            "sections": [
                {
                    "section_key": "system_design",
                    "evidence": [{"answer_message_id": 777, "round_no": 3}],
                }
            ],
            "next_action": {"type": "continue_current_topic"},
        }
        state = self.nodes.initial_chat_state(self.session, "candidate answer")

        execution = self.nodes.advance_execution_node(
            state,
            self.execution,
            answer,
            {"agent_run_id": 501},
        )

        self.assertIs(execution, self.execution)
        self.assertEqual(self.execution_service.advance_calls, [])
        self.assertIn("advance_execution_reused", state["completed_steps"])

    async def test_topic_judge_reuses_existing_agent_run(self):
        answer = message(777, "candidate answer", round_no=3)
        existing = SimpleNamespace(
            id=701,
            output_snapshot={"next_action": "move_next_section", "answer_quality": "medium"},
            output_schema_version="TopicJudgeResult.v1",
            evidence_refs=["interview_answer_777"],
            raw_response={"raw": "judge"},
        )
        self.agent_run_repo.runs[
            (
                10,
                "topic_completion_judge",
                tuple(sorted({"answer_message_id": 777, "execution_id": 40}.items())),
            )
        ] = existing
        state = self.nodes.initial_chat_state(self.session, "candidate answer")

        result = await self.nodes.topic_judge_node(
            state,
            self.session,
            answer,
            [],
            self.execution,
        )

        self.assertEqual(result["agent_run_id"], 701)
        self.assertEqual(result["next_action"], "move_next_section")
        self.assertEqual(result["schema_version"], "TopicJudgeResult.v1")
        self.assertEqual(self.topic_judge_agent.calls, [])
        self.assertIn("topic_judge_reused", state["completed_steps"])

    async def test_generate_followup_reuses_existing_agent_run(self):
        answer = message(888, "candidate answer", round_no=3)
        existing = SimpleNamespace(
            id=801,
            output_snapshot={"result": "existing followup"},
            output_schema_version="InterviewQuestion.v1",
            evidence_refs=["interview_answer_888"],
            raw_response={"raw": "followup"},
        )
        self.agent_run_repo.runs[
            (
                10,
                "followup",
                tuple(sorted({"answer_message_id": 888}.items())),
            )
        ] = existing
        state = self.nodes.initial_chat_state(self.session, "candidate answer")
        context = self.nodes.reload_followup_context_node(state, self.session, self.execution)

        fields = await self.nodes.generate_followup_node(
            state,
            self.session,
            answer,
            context,
        )

        self.assertEqual(fields["content"], "existing followup")
        self.assertEqual(fields["agent_run_id"], 801)
        self.assertEqual(fields["schema_version"], "InterviewQuestion.v1")
        self.assertEqual(self.interview_executor_agent.calls, [])
        self.assertIn("generate_followup_reused", state["completed_steps"])

    async def test_runtime_workflow_wraps_chat_loop(self):
        self.execution.state = {
            "sections": [{"section_key": "system_design", "evidence": []}],
            "next_action": {"type": "continue_current_topic"},
        }
        workflow = InterviewRuntimeWorkflow(self.nodes)

        result = await workflow.resume_with_user_input(
            session=self.session,
            message="candidate answer",
        )

        self.assertEqual(result.reply, "followup question")
        self.assertEqual(result.round_no, 4)
        self.assertEqual(result.answer_message_id, 100)
        self.assertEqual(result.assistant_message_id, 101)
        self.assertEqual(result.state["status"], "waiting_user")
        self.assertIn("save_user_answer", result.state["completed_steps"])
        self.assertIn("generate_followup", result.state["completed_steps"])
        self.assertIn("save_assistant_message", result.state["completed_steps"])


if __name__ == "__main__":
    unittest.main()
