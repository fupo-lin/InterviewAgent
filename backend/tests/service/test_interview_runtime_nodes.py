import unittest
import logging
from types import SimpleNamespace

from service.support import configure_backend_imports

configure_backend_imports()

from app.service.interview_runtime_nodes import InterviewRuntimeNodes
from app.service.interview_runtime_langgraph import LangGraphNotAvailable, StateGraph
from app.service.interview_runtime_router import InterviewRuntimeRouter
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
        self.between_rounds = []
        self.between_round_messages = []
        self.recent_rounds = []

    def latest_assistant_question_round_no(self, session_id):
        return 3

    def latest_completed_round_no(self, session_id):
        return self.latest_completed

    def list_recent_rounds(self, session_id, rounds):
        self.recent_rounds.append(rounds)
        return [message(30, "previous answer", round_no=2)]

    def list_between_rounds(self, session_id, from_round_no, to_round_no):
        self.between_rounds.append((from_round_no, to_round_no))
        return self.between_round_messages

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
    def __init__(self) -> None:
        self.latest = {}
        self.created = []

    def get_latest_by_session_id(self, session_id, summary_type):
        return self.latest.get(summary_type)

    def get_by_range(self, session_id, summary_type, from_round_no, to_round_no):
        return None

    def create(self, **kwargs):
        item = SimpleNamespace(id=800 + len(self.created), **kwargs)
        self.created.append(item)
        return item


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


class FakeSessionRepo:
    def __init__(self) -> None:
        self.finished = []

    def mark_finished(self, session):
        session.status = "finished"
        self.finished.append(session)
        return session


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


class FakeWorkflowRuntime:
    def __init__(self) -> None:
        self.run = None
        self.saved = []

    def load_or_create(self, **kwargs):
        if self.run:
            return self.run
        self.run = SimpleNamespace(
            workflow_run_id="workflow-run-1",
            workflow_id=kwargs["workflow_id"],
            thread_id=kwargs["thread_id"],
            project_id=kwargs["project_id"],
            session_id=kwargs["session_id"],
            state=kwargs["initial_state"],
        )
        return self.run

    def save(self, workflow_run, **kwargs):
        for key, value in kwargs.items():
            setattr(workflow_run, key, value)
        self.saved.append((workflow_run, kwargs))
        return workflow_run


class FakeExecutionService:
    def __init__(self) -> None:
        self.advance_calls = []
        self.next_action = "continue_current_topic"
        self.execution_status_after_advance = None

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
        if self.execution_status_after_advance:
            execution.status = self.execution_status_after_advance
        execution.state = {
            **(execution.state or {}),
            "next_action": {"type": self.next_action},
        }
        return execution

    def context_for_followup(self, execution, plan_content=None):
        return "execution context"

    def response(self, execution):
        next_action = ((execution.state or {}).get("next_action") or {}).get("type")
        return {"nextAction": next_action or "continue_current_topic"}


class FakeTopicJudgeAgent:
    def __init__(self, events=None) -> None:
        self.calls = []
        self.events = events

    async def run(self, agent_input):
        if self.events is not None:
            self.events.append("topic_judge_llm")
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


class StructuredMemoryTopicJudgeAgent:
    async def run(self, agent_input):
        return SimpleNamespace(
            output={
                "next_action": "continue_current_topic",
                "answer_quality": "high",
                "technical_highlights": [
                    {
                        "highlight": "candidate used idempotency keys",
                        "related_probe_point": "idempotency",
                        "missing_followup": "ask retry failure handling",
                        "priority": "high",
                        "confidence": "medium",
                    }
                ],
                "risk_signals": [
                    {
                        "content": "no latency metric was provided",
                        "probe_point": "metrics",
                        "suggestion": "ask for latency and failure rate",
                        "priority": "medium",
                    }
                ],
            },
            raw_response={"raw": "judge"},
            agent_run=SimpleNamespace(id=777),
            output_schema="TopicJudgeResult.v1",
            evidence_refs=["interview_answer_100"],
        )


class FakeSessionMemoryAgent:
    def __init__(self) -> None:
        self.calls = []

    async def run(self, agent_input):
        self.calls.append(agent_input)
        return SimpleNamespace(
            agent_run=SimpleNamespace(id=701 + len(self.calls)),
            message_fields=lambda: {
                "content": "memory summary",
                "raw_response": {"raw": "memory"},
                "agent_run_id": 701 + len(self.calls),
                "schema_version": "SessionMemory.v1",
                "evidence_refs": [],
            },
        )


class FakeInterviewExecutorAgent:
    def __init__(self, events=None) -> None:
        self.calls = []
        self.events = events

    async def run(self, agent_input):
        if self.events is not None:
            self.events.append("followup_llm")
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


class FailingInterviewExecutorAgent:
    async def run(self, agent_input):
        raise RuntimeError("followup unavailable")


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
            status="active",
            state={"next_action": {"type": "continue_current_topic"}},
        )
        self.message_repo = FakeMessageRepo()
        self.session_repo = FakeSessionRepo()
        self.execution_service = FakeExecutionService()
        self.agent_run_repo = FakeAgentRunRepo()
        self.topic_judge_agent = FakeTopicJudgeAgent()
        self.session_memory_agent = FakeSessionMemoryAgent()
        self.interview_executor_agent = FakeInterviewExecutorAgent()
        self.nodes = InterviewRuntimeNodes(
            message_repo=self.message_repo,
            summary_repo=FakeSummaryRepo(),
            execution_repo=FakeExecutionRepo(self.execution),
            session_repo=self.session_repo,
            plan_repo=FakePlanRepo(),
            execution_service=self.execution_service,
            topic_judge_agent=self.topic_judge_agent,
            session_memory_agent=self.session_memory_agent,
            interview_executor_agent=self.interview_executor_agent,
            agent_run_repo=self.agent_run_repo,
            logger_=logging.getLogger("test_interview_runtime_nodes"),
        )
        self.nodes.logger.disabled = True

    def test_runtime_workflow_rejects_sequential_fallback(self):
        with self.assertRaisesRegex(ValueError, "LangGraph-only"):
            InterviewRuntimeWorkflow(self.nodes, use_langgraph=False)

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
        self.assertEqual(len(self.nodes.execution_repo.save_calls), 2)
        self.assertEqual(
            self.execution.state["memory_refs"]["agent_run_ids"],
            [501, 601],
        )
        self.assertEqual(fields["content"], "followup question")
        self.assertEqual(assistant.content, "followup question")
        self.assertEqual(assistant.round_no, 4)
        self.assertEqual(state["last_topic_judge_agent_run_id"], 501)
        self.assertEqual(state["last_followup_agent_run_id"], 601)
        self.assertEqual(state["status"], "waiting_user")
        self.assertIn("save_user_answer", state["completed_steps"])
        self.assertIn("save_assistant_message", state["completed_steps"])
        self.assertEqual(len(self.message_repo.created), 2)
        self.assertIn("InterviewPlan mode: jd_resume", followup_context.plan_context)
        self.assertIn(
            "InterviewPlan mode: jd_resume",
            self.interview_executor_agent.calls[0].plan_context,
        )
        self.assertEqual(followup_context.execution_context, "execution context")
        self.assertEqual(self.message_repo.recent_rounds[-1], 4)

    async def test_refresh_memory_waits_until_fifteen_completed_rounds(self):
        state = self.nodes.initial_chat_state(self.session, "candidate answer")

        await self.nodes.refresh_memory_node(
            state,
            self.session,
            latest_completed_round_no=14,
        )

        self.assertEqual(self.session_memory_agent.calls, [])
        self.assertEqual(self.message_repo.between_rounds, [])
        self.assertIn("refresh_memory_skipped", state["completed_steps"])

    async def test_refresh_memory_uses_fifteen_round_interval_for_profile_and_summary(self):
        summary_repo = FakeSummaryRepo()
        self.nodes.summary_repo = summary_repo
        self.message_repo.between_round_messages = [
            message(201, "round 1 answer", round_no=1),
            message(215, "round 15 answer", round_no=15),
        ]
        state = self.nodes.initial_chat_state(self.session, "candidate answer")

        await self.nodes.refresh_memory_node(
            state,
            self.session,
            latest_completed_round_no=15,
        )

        self.assertEqual(
            [call.prompt_id for call in self.session_memory_agent.calls],
            ["candidate_profile", "conversation_summary"],
        )
        self.assertEqual(self.message_repo.between_rounds, [(1, 15), (1, 15)])
        self.assertEqual(
            [item.summary_type for item in summary_repo.created],
            ["candidate_profile", "conversation"],
        )
        self.assertIn("refresh_memory", state["completed_steps"])

    async def test_refresh_memory_reuses_summary_until_fifteen_new_rounds(self):
        summary_repo = FakeSummaryRepo()
        summary_repo.latest["candidate_profile"] = SimpleNamespace(
            id=901,
            content="profile",
            to_round_no=10,
        )
        summary_repo.latest["conversation"] = SimpleNamespace(
            id=902,
            content="summary",
            to_round_no=10,
        )
        self.nodes.summary_repo = summary_repo
        state = self.nodes.initial_chat_state(self.session, "candidate answer")

        await self.nodes.refresh_memory_node(
            state,
            self.session,
            latest_completed_round_no=24,
        )

        self.assertEqual(self.session_memory_agent.calls, [])
        self.assertEqual(self.message_repo.between_rounds, [])
        self.assertEqual(summary_repo.created, [])
        self.assertIn("refresh_memory", state["completed_steps"])

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

    async def test_runtime_context_restores_open_threads_from_execution_state(self):
        self.execution.state = {
            "next_action": {"type": "continue_current_topic"},
            "open_threads": [
                {
                    "id": "thread-persisted",
                    "source_message_id": 100,
                    "round_no": 3,
                    "section_key": "system_design",
                    "probe_point": "idempotency",
                    "highlight": "candidate mentioned idempotency",
                    "missing_detail": "ask retry failure handling",
                    "priority": "high",
                    "status": "open",
                }
            ],
            "memory_refs": {"conversation_summary_id": 902},
        }
        state = self.nodes.initial_chat_state(self.session, "candidate answer")

        context = self.nodes.load_runtime_context_node(state, self.session)

        self.assertEqual(state["open_threads"][0]["id"], "thread-persisted")
        self.assertEqual(state["open_threads"][0]["memory_type"], "open_followup")
        self.assertEqual(
            state["open_threads"][0]["content"],
            "candidate mentioned idempotency",
        )
        self.assertEqual(context.open_threads[0]["id"], "thread-persisted")
        self.assertIn("OpenFollowupThreads:", context.execution_context)
        self.assertIn("candidate mentioned idempotency", context.execution_context)
        self.assertEqual(state["memory_refs"]["conversation_summary_id"], None)
        self.assertEqual(state["memory_refs"]["execution_id"], 40)

    async def test_topic_judge_normalizes_structured_memory_items(self):
        self.nodes.topic_judge_agent = StructuredMemoryTopicJudgeAgent()
        state = self.nodes.initial_chat_state(self.session, "candidate answer")
        answer = message(888, "I used idempotency keys.", round_no=3)

        result = await self.nodes.topic_judge_node(
            state,
            self.session,
            answer,
            recent_history=[answer],
            execution=self.execution,
        )

        self.assertEqual(result["agent_run_id"], 777)
        self.assertEqual(len(state["open_threads"]), 2)
        first = state["open_threads"][0]
        self.assertEqual(first["memory_type"], "technical_highlight")
        self.assertEqual(first["content"], "candidate used idempotency keys")
        self.assertEqual(first["missing_detail"], "ask retry failure handling")
        self.assertEqual(first["source_message_id"], 888)
        self.assertEqual(first["source_agent_run_id"], 777)
        self.assertEqual(first["metadata"]["source_field"], "technical_highlights")
        second = state["open_threads"][1]
        self.assertEqual(second["memory_type"], "risk_signal")
        self.assertEqual(second["content"], "no latency metric was provided")
        self.assertEqual(second["missing_detail"], "ask for latency and failure rate")
        self.assertEqual(self.execution.state["open_threads"], state["open_threads"])

    async def test_open_thread_lifecycle_selects_asks_and_closes_after_answer(self):
        state = self.nodes.initial_chat_state(self.session, "candidate answer")
        state["open_threads"] = [
            {
                "id": "thread-1",
                "source_message_id": 100,
                "round_no": 3,
                "section_key": "system_design",
                "probe_point": "idempotency",
                "highlight": "candidate mentioned idempotency",
                "missing_detail": "ask failure scenario",
                "priority": "high",
                "status": "open",
            }
        ]
        answer = message(777, "candidate answer", round_no=3)
        context = self.nodes.reload_followup_context_node(
            state,
            self.session,
            self.execution,
        )

        fields = await self.nodes.generate_followup_node(
            state,
            self.session,
            answer,
            context,
        )

        self.assertEqual(state["open_threads"][0]["status"], "selected")
        self.assertEqual(state["open_threads"][0]["selected_agent_run_id"], 601)
        self.assertEqual(self.execution.state["open_threads"][0]["status"], "selected")

        assistant = self.nodes.save_assistant_message_node(
            state,
            self.session,
            round_no=4,
            message_fields=fields,
            execution=self.execution,
        )

        self.assertEqual(state["open_threads"][0]["status"], "asked")
        self.assertEqual(state["open_threads"][0]["asked_message_id"], assistant.id)
        self.assertEqual(state["open_threads"][0]["asked_round_no"], 4)
        self.assertEqual(self.execution.state["open_threads"][0]["status"], "asked")
        self.assertEqual(
            self.execution.state["open_threads"][0]["asked_message_id"],
            assistant.id,
        )

        next_answer = message(778, "I used idempotency keys for retries.", round_no=4)
        await self.nodes.topic_judge_node(
            state,
            self.session,
            next_answer,
            recent_history=[next_answer],
            execution=self.execution,
        )

        self.assertEqual(state["open_threads"][0]["status"], "closed")
        self.assertEqual(state["open_threads"][0]["answered_message_id"], 778)
        self.assertEqual(self.execution.state["open_threads"][0]["status"], "closed")
        self.assertEqual(self.execution.state["open_threads"][0]["answered_message_id"], 778)

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

    async def test_finalize_interview_node_marks_session_and_execution_finished(self):
        answer = message(777, "final answer", round_no=3)
        state = self.nodes.initial_chat_state(self.session, "final answer")
        state["route_after_advance"] = InterviewRuntimeRouter.FINISHED
        state["route_after_advance_reason"] = "next_action_finished"

        assistant = self.nodes.finalize_interview_node(
            state=state,
            session=self.session,
            answer_message=answer,
            execution=self.execution,
        )

        self.assertEqual(assistant.role_type, "assistant")
        self.assertEqual(assistant.message_type, "summary")
        self.assertEqual(assistant.round_no, 4)
        self.assertEqual(self.session.status, "finished")
        self.assertEqual(self.execution.status, "finished")
        self.assertEqual(self.execution.state["next_action"]["type"], "finished")
        self.assertEqual(state["status"], "finished")
        self.assertEqual(state["active_step"], None)
        self.assertEqual(state["last_assistant_message_id"], assistant.id)
        self.assertIn("finalize_interview", state["completed_steps"])
        self.assertEqual(self.session_repo.finished, [self.session])

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

    async def test_wrap_up_nodes_generate_and_save_wrap_up_message(self):
        answer = message(888, "candidate answer", round_no=3)
        state = self.nodes.initial_chat_state(self.session, "candidate answer")
        state["route_after_advance"] = InterviewRuntimeRouter.WRAP_UP
        state["route_after_advance_reason"] = "next_action_wrap_up_interview"
        context = self.nodes.reload_followup_context_node(state, self.session, self.execution)

        fields = await self.nodes.generate_wrap_up_question_node(
            state,
            self.session,
            answer,
            context,
        )
        assistant = self.nodes.save_wrap_up_message_node(
            state,
            self.session,
            4,
            fields,
            self.execution,
        )

        self.assertEqual(fields["content"], "followup question")
        self.assertEqual(assistant.message_type, "wrap_up")
        self.assertEqual(assistant.raw_response["source"], "interview_runtime_wrap_up")
        self.assertEqual(
            assistant.raw_response["route_after_advance"],
            InterviewRuntimeRouter.WRAP_UP,
        )
        self.assertIn("generate_wrap_up_question", state["completed_steps"])
        self.assertIn("save_wrap_up_message", state["completed_steps"])
        self.assertNotIn("generate_followup", state["completed_steps"])
        self.assertNotIn("save_assistant_message", state["completed_steps"])

    async def test_runtime_workflow_wraps_chat_loop(self):
        self.execution.state = {
            "sections": [{"section_key": "system_design", "evidence": []}],
            "next_action": {"type": "continue_current_topic"},
        }
        runtime = FakeWorkflowRuntime()
        workflow = InterviewRuntimeWorkflow(self.nodes, runtime=runtime)

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
        self.assertEqual(result.state["workflow_run_id"], "workflow-run-1")
        self.assertEqual(runtime.saved[-1][1]["current_step"], "wait_user_answer")
        self.assertEqual(runtime.saved[-1][1]["status"], "waiting_user")
        self.assertEqual(runtime.saved[-1][1]["state"]["status"], "waiting_user")
        self.assertEqual(self.topic_judge_agent.calls[0].workflow_run_id, "workflow-run-1")
        self.assertEqual(self.interview_executor_agent.calls[0].workflow_run_id, "workflow-run-1")

    async def test_runtime_workflow_commits_between_external_llm_steps(self):
        events = []
        self.nodes.topic_judge_agent = FakeTopicJudgeAgent(events)
        self.nodes.interview_executor_agent = FakeInterviewExecutorAgent(events)
        self.execution.state = {
            "sections": [{"section_key": "system_design", "evidence": []}],
            "next_action": {"type": "continue_current_topic"},
        }
        runtime = FakeWorkflowRuntime()
        workflow = InterviewRuntimeWorkflow(
            self.nodes,
            runtime=runtime,
            commit_after_step=lambda: events.append(
                f"commit:{runtime.saved[-1][1]['current_step']}"
            ),
        )

        result = await workflow.resume_with_user_input(
            session=self.session,
            message="candidate answer",
        )

        self.assertEqual(result.reply, "followup question")
        self.assertLess(
            events.index("commit:save_user_answer"),
            events.index("topic_judge_llm"),
        )
        self.assertLess(
            events.index("commit:advance_execution"),
            events.index("followup_llm"),
        )
        self.assertIn("commit:wait_user_answer", events)

    async def test_runtime_workflow_records_route_after_advance(self):
        self.execution_service.next_action = "move_next_section"
        self.execution.state = {
            "sections": [{"section_key": "system_design", "evidence": []}],
            "next_action": {"type": "continue_current_topic"},
        }
        runtime = FakeWorkflowRuntime()
        workflow = InterviewRuntimeWorkflow(self.nodes, runtime=runtime)

        result = await workflow.resume_with_user_input(
            session=self.session,
            message="candidate answer",
        )

        self.assertEqual(
            result.state["route_after_advance"],
            InterviewRuntimeRouter.MOVE_NEXT_SECTION,
        )
        self.assertEqual(
            result.state["route_after_advance_reason"],
            "next_action_move_next_section",
        )

    async def test_runtime_workflow_finished_route_finalizes_without_followup(self):
        self.execution_service.next_action = "finished"
        self.execution_service.execution_status_after_advance = "finished"
        self.execution.state = {
            "sections": [{"section_key": "system_design", "evidence": []}],
            "next_action": {"type": "continue_current_topic"},
        }
        runtime = FakeWorkflowRuntime()
        workflow = InterviewRuntimeWorkflow(self.nodes, runtime=runtime)

        result = await workflow.resume_with_user_input(
            session=self.session,
            message="final candidate answer",
        )

        self.assertEqual(result.round_no, 4)
        self.assertEqual(result.state["status"], "finished")
        self.assertEqual(
            result.state["route_after_advance"],
            InterviewRuntimeRouter.FINISHED,
        )
        self.assertIn("finalize_interview", result.state["completed_steps"])
        self.assertNotIn("generate_followup", result.state["completed_steps"])
        self.assertEqual(self.interview_executor_agent.calls, [])
        self.assertEqual(self.message_repo.created[-1].message_type, "summary")
        self.assertEqual(runtime.saved[-1][1]["current_step"], "complete")
        self.assertEqual(runtime.saved[-1][1]["status"], "finished")
        self.assertEqual(self.session.status, "finished")

    async def test_runtime_workflow_wrap_up_route_uses_wrap_up_steps(self):
        self.execution_service.next_action = "wrap_up_interview"
        self.execution.state = {
            "sections": [{"section_key": "system_design", "evidence": []}],
            "next_action": {"type": "continue_current_topic"},
        }
        runtime = FakeWorkflowRuntime()
        workflow = InterviewRuntimeWorkflow(self.nodes, runtime=runtime)

        result = await workflow.resume_with_user_input(
            session=self.session,
            message="candidate answer",
        )

        self.assertEqual(result.reply, "followup question")
        self.assertEqual(result.state["status"], "waiting_user")
        self.assertEqual(
            result.state["route_after_advance"],
            InterviewRuntimeRouter.WRAP_UP,
        )
        self.assertIn("generate_wrap_up_question", result.state["completed_steps"])
        self.assertIn("save_wrap_up_message", result.state["completed_steps"])
        self.assertNotIn("generate_followup", result.state["completed_steps"])
        self.assertNotIn("save_assistant_message", result.state["completed_steps"])
        self.assertEqual(self.message_repo.created[-1].message_type, "wrap_up")
        self.assertEqual(runtime.saved[-1][1]["current_step"], "wait_user_answer")
        self.assertEqual(runtime.saved[-1][1]["status"], "waiting_user")

    async def test_runtime_workflow_emits_step_events(self):
        events = []
        self.execution.state = {
            "sections": [{"section_key": "system_design", "evidence": []}],
            "next_action": {"type": "continue_current_topic"},
        }
        runtime = FakeWorkflowRuntime()
        workflow = InterviewRuntimeWorkflow(
            self.nodes,
            runtime=runtime,
            on_step=events.append,
        )

        result = await workflow.resume_with_user_input(
            session=self.session,
            message="candidate answer",
        )

        self.assertEqual(result.reply, "followup question")
        step_names = [event["step"] for event in events]
        self.assertIn("save_user_answer", step_names)
        self.assertIn("advance_execution", step_names)
        self.assertIn("wait_user_answer", step_names)
        advance_event = events[step_names.index("advance_execution")]
        self.assertEqual(advance_event["event"], "step")
        self.assertEqual(advance_event["workflowRunId"], "workflow-run-1")
        self.assertEqual(
            advance_event["routeAfterAdvance"],
            InterviewRuntimeRouter.CONTINUE_TOPIC,
        )
        self.assertEqual(events[-1]["status"], "waiting_user")

    async def test_runtime_workflow_resumes_from_persisted_state_for_new_turn(self):
        self.execution.state = {
            "sections": [{"section_key": "system_design", "evidence": []}],
            "next_action": {"type": "continue_current_topic"},
        }
        runtime = FakeWorkflowRuntime()
        runtime.run = SimpleNamespace(
            workflow_run_id="workflow-run-1",
            workflow_id="interview_runtime",
            thread_id="interview:session-uid",
            project_id=1,
            session_id=10,
            status="waiting_user",
            current_step="wait_user_answer",
            state={
                "workflow_id": "interview_runtime",
                "thread_id": "interview:session-uid",
                "workflow_run_id": "workflow-run-1",
                "status": "waiting_user",
                "incoming_user_input": "old answer",
                "last_assistant_message_id": 444,
                "completed_steps": ["old_turn_step"],
                "failed_steps": ["old_turn_failure"],
                "last_memory_agent_run_ids": [333],
                "last_error": {"step_id": "old", "message": "old failure"},
            },
        )
        workflow = InterviewRuntimeWorkflow(self.nodes, runtime=runtime)

        result = await workflow.resume_with_user_input(
            session=self.session,
            message="second answer",
        )

        start_state = runtime.saved[0][1]["state"]
        self.assertEqual(start_state["workflow_run_id"], "workflow-run-1")
        self.assertEqual(start_state["incoming_user_input"], "second answer")
        self.assertEqual(start_state["last_assistant_message_id"], 444)
        self.assertEqual(start_state["completed_steps"], [])
        self.assertEqual(start_state["failed_steps"], [])
        self.assertEqual(start_state["last_memory_agent_run_ids"], [])
        self.assertIsNone(start_state["last_error"])
        self.assertEqual(start_state["resume_reason"], "new_user_input")
        self.assertEqual(start_state["resume_from_step"], "wait_user_answer")
        self.assertEqual(result.state["workflow_run_id"], "workflow-run-1")
        self.assertNotIn("old_turn_step", result.state["completed_steps"])
        self.assertNotIn("old_turn_failure", result.state["failed_steps"])

    async def test_runtime_workflow_retries_unfinished_turn_from_persisted_state(self):
        existing_answer = message(999, "original interrupted answer", round_no=3)
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
        runtime = FakeWorkflowRuntime()
        runtime.run = SimpleNamespace(
            workflow_run_id="workflow-run-1",
            workflow_id="interview_runtime",
            thread_id="interview:session-uid",
            project_id=1,
            session_id=10,
            status="running",
            current_step="topic_judge",
            state={
                "workflow_id": "interview_runtime",
                "thread_id": "interview:session-uid",
                "workflow_run_id": "workflow-run-1",
                "status": "running",
                "incoming_user_input": "original interrupted answer",
                "last_user_message_id": 999,
                "completed_steps": ["save_user_answer", "load_runtime_context"],
                "failed_steps": [],
                "last_error": None,
            },
        )
        workflow = InterviewRuntimeWorkflow(self.nodes, runtime=runtime)

        result = await workflow.resume_with_user_input(
            session=self.session,
            message="new text that should not replace interrupted turn",
        )

        start_state = runtime.saved[0][1]["state"]
        self.assertEqual(start_state["incoming_user_input"], "original interrupted answer")
        self.assertEqual(start_state["resume_reason"], "unfinished_turn")
        self.assertEqual(start_state["resume_from_step"], "topic_judge")
        self.assertEqual(result.answer_message_id, 999)
        self.assertEqual(self.message_repo.created[0].role_type, "assistant")
        self.assertEqual(self.execution_service.advance_calls, [])
        self.assertIn("save_user_answer_reused", result.state["completed_steps"])
        self.assertIn("advance_execution_reused", result.state["completed_steps"])

    async def test_runtime_workflow_retries_failed_turn_from_persisted_state(self):
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
        runtime = FakeWorkflowRuntime()
        runtime.run = SimpleNamespace(
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
        workflow = InterviewRuntimeWorkflow(self.nodes, runtime=runtime)

        result = await workflow.resume_with_user_input(
            session=self.session,
            message="new answer that should wait for next turn",
        )

        start_state = runtime.saved[0][1]["state"]
        self.assertEqual(start_state["incoming_user_input"], "answer before followup failure")
        self.assertEqual(start_state["resume_reason"], "failed_retry")
        self.assertEqual(start_state["resume_from_step"], "generate_followup")
        self.assertEqual(start_state["failed_steps"], [])
        self.assertIsNone(start_state["last_error"])
        self.assertEqual(result.answer_message_id, 999)
        self.assertEqual(result.reply, "followup question")
        self.assertEqual(runtime.saved[-1][1]["status"], "waiting_user")
        self.assertEqual(self.execution_service.advance_calls, [])
        self.assertIn("save_user_answer_reused", result.state["completed_steps"])
        self.assertIn("advance_execution_reused", result.state["completed_steps"])

    async def test_runtime_workflow_marks_blocking_failure(self):
        self.nodes.interview_executor_agent = FailingInterviewExecutorAgent()
        self.execution.state = {
            "sections": [{"section_key": "system_design", "evidence": []}],
            "next_action": {"type": "continue_current_topic"},
        }
        runtime = FakeWorkflowRuntime()
        workflow = InterviewRuntimeWorkflow(self.nodes, runtime=runtime)

        with self.assertRaisesRegex(RuntimeError, "followup unavailable"):
            await workflow.resume_with_user_input(
                session=self.session,
                message="candidate answer",
            )

        failed_save = runtime.saved[-1][1]
        self.assertEqual(failed_save["current_step"], "generate_followup")
        self.assertEqual(failed_save["status"], "failed")
        self.assertEqual(failed_save["state"]["status"], "failed")
        self.assertEqual(failed_save["last_error"]["step_id"], "generate_followup")
        self.assertEqual(failed_save["last_error"]["message"], "followup unavailable")
        self.assertIn("generate_followup", failed_save["state"]["failed_steps"])
        self.assertNotIn("last_assistant_message_id", failed_save["state"])

    async def test_runtime_workflow_can_enable_langgraph_path(self):
        self.execution.state = {
            "sections": [{"section_key": "system_design", "evidence": []}],
            "next_action": {"type": "continue_current_topic"},
        }
        runtime = FakeWorkflowRuntime()
        workflow = InterviewRuntimeWorkflow(
            self.nodes,
            runtime=runtime,
            use_langgraph=True,
        )

        if StateGraph is None:
            with self.assertRaises(LangGraphNotAvailable):
                await workflow.resume_with_user_input(
                    session=self.session,
                    message="candidate answer",
                )
            return

        result = await workflow.resume_with_user_input(
                session=self.session,
                message="candidate answer",
        )

        self.assertEqual(result.reply, "followup question")
        self.assertEqual(result.round_no, 4)
        self.assertEqual(result.state["status"], "waiting_user")
        self.assertEqual(result.state["workflow_run_id"], "workflow-run-1")
        self.assertEqual(runtime.saved[-1][1]["current_step"], "wait_user_answer")
        self.assertEqual(runtime.saved[-1][1]["status"], "waiting_user")
        self.assertEqual(self.topic_judge_agent.calls[0].workflow_run_id, "workflow-run-1")
        self.assertEqual(self.interview_executor_agent.calls[0].workflow_run_id, "workflow-run-1")

    async def test_langgraph_path_uses_commit_after_step_when_available(self):
        if StateGraph is None:
            return

        events = []
        self.nodes.topic_judge_agent = FakeTopicJudgeAgent(events)
        self.nodes.interview_executor_agent = FakeInterviewExecutorAgent(events)
        self.execution.state = {
            "sections": [{"section_key": "system_design", "evidence": []}],
            "next_action": {"type": "continue_current_topic"},
        }
        runtime = FakeWorkflowRuntime()
        workflow = InterviewRuntimeWorkflow(
            self.nodes,
            runtime=runtime,
            use_langgraph=True,
            commit_after_step=lambda: events.append(
                f"commit:{runtime.saved[-1][1]['current_step']}"
            ),
        )

        result = await workflow.resume_with_user_input(
            session=self.session,
            message="candidate answer",
        )

        self.assertEqual(result.reply, "followup question")
        self.assertLess(
            events.index("commit:save_user_answer"),
            events.index("topic_judge_llm"),
        )
        self.assertLess(
            events.index("commit:advance_execution"),
            events.index("followup_llm"),
        )
        self.assertIn("commit:wait_user_answer", events)

    async def test_langgraph_finished_route_finalizes_without_followup_when_available(self):
        if StateGraph is None:
            return

        self.execution_service.next_action = "finished"
        self.execution_service.execution_status_after_advance = "finished"
        self.execution.state = {
            "sections": [{"section_key": "system_design", "evidence": []}],
            "next_action": {"type": "continue_current_topic"},
        }
        runtime = FakeWorkflowRuntime()
        workflow = InterviewRuntimeWorkflow(
            self.nodes,
            runtime=runtime,
            use_langgraph=True,
        )

        result = await workflow.resume_with_user_input(
            session=self.session,
            message="final candidate answer",
        )

        self.assertEqual(result.state["status"], "finished")
        self.assertEqual(
            result.state["route_after_advance"],
            InterviewRuntimeRouter.FINISHED,
        )
        self.assertIn("finalize_interview", result.state["completed_steps"])
        self.assertNotIn("generate_followup", result.state["completed_steps"])
        self.assertEqual(self.interview_executor_agent.calls, [])
        self.assertEqual(self.message_repo.created[-1].message_type, "summary")
        self.assertEqual(runtime.saved[-1][1]["current_step"], "complete")
        self.assertEqual(runtime.saved[-1][1]["status"], "finished")

    async def test_langgraph_wrap_up_route_uses_wrap_up_steps_when_available(self):
        if StateGraph is None:
            return

        self.execution_service.next_action = "wrap_up_interview"
        self.execution.state = {
            "sections": [{"section_key": "system_design", "evidence": []}],
            "next_action": {"type": "continue_current_topic"},
        }
        runtime = FakeWorkflowRuntime()
        workflow = InterviewRuntimeWorkflow(
            self.nodes,
            runtime=runtime,
            use_langgraph=True,
        )

        result = await workflow.resume_with_user_input(
            session=self.session,
            message="candidate answer",
        )

        self.assertEqual(result.state["status"], "waiting_user")
        self.assertEqual(
            result.state["route_after_advance"],
            InterviewRuntimeRouter.WRAP_UP,
        )
        self.assertIn("generate_wrap_up_question", result.state["completed_steps"])
        self.assertIn("save_wrap_up_message", result.state["completed_steps"])
        self.assertNotIn("generate_followup", result.state["completed_steps"])
        self.assertNotIn("save_assistant_message", result.state["completed_steps"])
        self.assertEqual(self.message_repo.created[-1].message_type, "wrap_up")
        self.assertEqual(runtime.saved[-1][1]["current_step"], "wait_user_answer")

    async def test_langgraph_path_resumes_from_persisted_state_when_available(self):
        if StateGraph is None:
            return

        self.execution.state = {
            "sections": [{"section_key": "system_design", "evidence": []}],
            "next_action": {"type": "continue_current_topic"},
        }
        runtime = FakeWorkflowRuntime()
        runtime.run = SimpleNamespace(
            workflow_run_id="workflow-run-1",
            workflow_id="interview_runtime",
            thread_id="interview:session-uid",
            project_id=1,
            session_id=10,
            status="waiting_user",
            current_step="wait_user_answer",
            state={
                "workflow_id": "interview_runtime",
                "thread_id": "interview:session-uid",
                "workflow_run_id": "workflow-run-1",
                "status": "waiting_user",
                "incoming_user_input": "old answer",
                "last_assistant_message_id": 444,
                "completed_steps": ["old_turn_step"],
                "failed_steps": ["old_turn_failure"],
                "last_error": {"step_id": "old", "message": "old failure"},
            },
        )
        workflow = InterviewRuntimeWorkflow(
            self.nodes,
            runtime=runtime,
            use_langgraph=True,
        )

        result = await workflow.resume_with_user_input(
            session=self.session,
            message="second answer",
        )

        start_state = runtime.saved[0][1]["state"]
        self.assertEqual(start_state["workflow_run_id"], "workflow-run-1")
        self.assertEqual(start_state["incoming_user_input"], "second answer")
        self.assertEqual(start_state["last_assistant_message_id"], 444)
        self.assertEqual(start_state["completed_steps"], [])
        self.assertEqual(start_state["failed_steps"], [])
        self.assertIsNone(start_state["last_error"])
        self.assertEqual(start_state["resume_reason"], "new_user_input")
        self.assertEqual(start_state["resume_from_step"], "wait_user_answer")
        self.assertEqual(result.state["workflow_run_id"], "workflow-run-1")
        self.assertNotIn("old_turn_step", result.state["completed_steps"])

    async def test_langgraph_path_retries_failed_turn_from_persisted_state_when_available(self):
        if StateGraph is None:
            return

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
        runtime = FakeWorkflowRuntime()
        runtime.run = SimpleNamespace(
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
            runtime=runtime,
            use_langgraph=True,
        )

        result = await workflow.resume_with_user_input(
            session=self.session,
            message="new answer that should wait for next turn",
        )

        start_state = runtime.saved[0][1]["state"]
        self.assertEqual(start_state["incoming_user_input"], "answer before followup failure")
        self.assertEqual(start_state["resume_reason"], "failed_retry")
        self.assertEqual(start_state["resume_from_step"], "generate_followup")
        self.assertEqual(start_state["failed_steps"], [])
        self.assertIsNone(start_state["last_error"])
        self.assertEqual(result.answer_message_id, 999)
        self.assertEqual(result.reply, "followup question")
        self.assertEqual(runtime.saved[-1][1]["current_step"], "wait_user_answer")
        self.assertEqual(runtime.saved[-1][1]["status"], "waiting_user")
        self.assertEqual(self.execution_service.advance_calls, [])
        self.assertIn("save_user_answer_reused", result.state["completed_steps"])
        self.assertIn("advance_execution_reused", result.state["completed_steps"])
        self.assertEqual(self.topic_judge_agent.calls[0].workflow_run_id, "workflow-run-1")
        self.assertEqual(self.interview_executor_agent.calls[0].workflow_run_id, "workflow-run-1")


if __name__ == "__main__":
    unittest.main()
