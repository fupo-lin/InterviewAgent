import unittest
from types import SimpleNamespace

from service.support import configure_backend_imports

configure_backend_imports()

from app.service.agent_run_service import AgentRunExecutor
from app.service.agent_runtime import AgentRuntimeConfig
from app.service.agent_tools import ToolDefinition, ToolRegistry, ToolRuntime
from app.service.evidence_service import EvidencePacketBuilder
from app.service.retrieval_contract import RetrievedKnowledge
from app.service.runtime_agents import (
    FirstQuestionAgentInput,
    FollowupAgentInput,
    InterviewExecutorAgent,
    SessionMemoryAgent,
    SessionMemoryAgentInput,
    TopicJudgeAgent,
    TopicJudgeAgentInput,
)


class FakeRecorder:
    def __init__(self) -> None:
        self.success_calls = []

    def record_success(self, **kwargs):
        self.success_calls.append(kwargs)
        return SimpleNamespace(id=1000 + len(self.success_calls))

    def record_failure(self, **kwargs):
        raise AssertionError("failure was not expected")


class FakeLLM:
    model = "test-model"

    def __init__(self) -> None:
        self.first_question_calls = []
        self.followup_calls = []
        self.candidate_profile_calls = []
        self.conversation_summary_calls = []
        self.topic_judge_calls = []

    async def generate_first_question(self, role_name, plan_context=None):
        self.first_question_calls.append((role_name, plan_context))
        return "first question", {"raw": "first_question"}

    async def generate_followup(
        self,
        role_name,
        user_answer,
        history,
        candidate_profile=None,
        conversation_summary=None,
        plan_context=None,
        execution_context=None,
    ):
        self.followup_calls.append(
            {
                "role_name": role_name,
                "user_answer": user_answer,
                "history": history,
                "candidate_profile": candidate_profile,
                "conversation_summary": conversation_summary,
                "plan_context": plan_context,
                "execution_context": execution_context,
            }
        )
        return "followup question", {"raw": "followup"}

    async def generate_candidate_profile(self, previous_profile, new_messages):
        self.candidate_profile_calls.append((previous_profile, new_messages))
        return "candidate memory", {"raw": "candidate_profile"}

    async def generate_conversation_summary(self, previous_summary, new_messages):
        self.conversation_summary_calls.append((previous_summary, new_messages))
        return "conversation memory", {"raw": "conversation_summary"}

    async def judge_topic_completion(self, **kwargs):
        self.topic_judge_calls.append(kwargs)
        return {
            "topic_status": "complete",
            "answer_quality": "high",
            "covered_probe_points": ["idempotency"],
            "next_action": "move_next_section",
        }, {"raw": "topic_judge"}


class FakeToolCallingLLM(FakeLLM):
    async def generate_followup_with_tool_calling(
        self,
        role_name,
        user_answer,
        history,
        *,
        tool_runtime,
        tool_context,
        allowed_tool_names=None,
        candidate_profile=None,
        conversation_summary=None,
        plan_context=None,
        execution_context=None,
        retrieved_evidence_context=None,
        open_threads=None,
    ):
        self.followup_calls.append(
            {
                "role_name": role_name,
                "user_answer": user_answer,
                "history": history,
                "allowed_tool_names": tuple(allowed_tool_names or ()),
                "open_threads": open_threads,
            }
        )
        return "tool-aware followup", {
            "tool_calling": {
                "mode": "model_driven",
                "trace": [
                    {
                        "tool_name": "get_previous_answer",
                        "arguments": {"query": user_answer},
                        "result": {"status": "success"},
                    }
                ],
            }
        }

    async def judge_topic_completion_with_tool_calling(
        self,
        *,
        current_section,
        execution_state,
        user_answer,
        recent_history,
        tool_runtime,
        tool_context,
        allowed_tool_names=None,
        retrieved_evidence_context=None,
    ):
        self.topic_judge_calls.append(
            {
                "current_section": current_section,
                "execution_state": execution_state,
                "user_answer": user_answer,
                "recent_history": recent_history,
                "allowed_tool_names": tuple(allowed_tool_names or ()),
                "retrieved_evidence_context": retrieved_evidence_context,
            }
        )
        return {
            "topic_status": "partial",
            "answer_quality": "medium",
            "covered_probe_points": ["idempotency"],
            "missing_probe_points": ["failure recovery"],
            "next_action": "continue_current_topic",
            "reason": "needs one follow-up",
        }, {
            "tool_calling": {
                "mode": "model_driven",
                "trace": [
                    {
                        "tool_name": "get_previous_answer",
                        "arguments": {"query": user_answer},
                        "result": {"status": "success"},
                    }
                ],
            }
        }


def message(
    message_id: int,
    content: str,
    role_type: str = "user",
    session_id: int = 10,
    round_no: int = 1,
):
    return SimpleNamespace(
        id=message_id,
        session_id=session_id,
        role_type=role_type,
        message_type="answer" if role_type == "user" else "question",
        round_no=round_no,
        content=content,
    )


class RuntimeAgentTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.recorder = FakeRecorder()
        self.executor = AgentRunExecutor(db=SimpleNamespace(), recorder=self.recorder)
        self.evidence_builder = EvidencePacketBuilder()
        self.llm = FakeLLM()
        self.config = AgentRuntimeConfig(model_name=self.llm.model)

    def assert_contract_ok(
        self,
        success: dict,
        input_schema: str,
        output_schema: str,
    ) -> None:
        contract = success["input_snapshot"]["agent_contract_validation"]
        self.assertEqual(contract["input_schema"], input_schema)
        self.assertEqual(contract["output_schema"], output_schema)
        self.assertTrue(contract["input_ok"])
        self.assertTrue(contract["output_ok"])
        self.assertEqual(contract["errors"], [])

    async def test_interview_executor_agent_generates_first_question(self):
        agent = InterviewExecutorAgent(self.executor, self.evidence_builder, self.llm, self.config)
        session = SimpleNamespace(id=10, project_id=1, interview_plan_id=20)
        plan = SimpleNamespace(id=20)

        result = await agent.run(
            FirstQuestionAgentInput(
                session=session,
                role_name="Backend Engineer",
                plan_context="plan context",
                plan=plan,
            )
        )

        self.assertEqual(result.output, "first question")
        self.assertEqual(result.raw_response, {"raw": "first_question"})
        self.assertEqual(result.definition.prompt_id, "interviewer")
        self.assertEqual(result.output_schema, "InterviewQuestion.v1")
        self.assertEqual(result.message_fields()["content"], "first question")
        self.assertEqual(self.llm.first_question_calls, [("Backend Engineer", "plan context")])
        self.assertEqual(result.evidence_refs, [])
        success = self.recorder.success_calls[0]
        self.assertEqual(success["definition"].owner_agent, "InterviewExecutorAgent")
        self.assertEqual(success["context_refs"]["interview_plan_id"], 20)
        self.assertEqual(
            success["input_snapshot"]["workflow_context"]["step_id"],
            "first_question",
        )
        self.assert_contract_ok(success, "InterviewExecutorInputV1", "InterviewQuestionOutputV1")

    async def test_interview_executor_agent_generates_followup(self):
        agent = InterviewExecutorAgent(self.executor, self.evidence_builder, self.llm, self.config)
        session = SimpleNamespace(
            id=10,
            project_id=1,
            role_name="Backend Engineer",
            interview_plan_id=20,
        )
        answer_message = message(
            104,
            "I handled retry and idempotency.",
            round_no=6,
        )
        recent_history = [
            message(103, "Previous answer", round_no=5),
            answer_message,
        ]
        execution = SimpleNamespace(
            id=30,
            state={
                "sections": [
                    {
                        "section_key": "tech_foundation",
                        "evidence": [
                            {
                                "round_no": 5,
                                "answer_excerpt": "retry handling",
                                "covered_probe_points": ["Kafka retry"],
                            }
                        ],
                    }
                ]
            },
        )

        result = await agent.run(
            FollowupAgentInput(
                session=session,
                answer_message=answer_message,
                recent_history=recent_history,
                candidate_profile="candidate memory",
                conversation_summary="conversation memory",
                plan_context="plan context",
                execution_context="execution context",
                candidate_profile_id=201,
                conversation_summary_id=202,
                execution=execution,
                workflow_run_id="interview_runtime_live_1",
            )
        )

        self.assertEqual(result.output, "followup question")
        self.assertEqual(result.raw_response, {"raw": "followup"})
        self.assertEqual(result.definition.prompt_id, "followup")
        self.assertEqual(result.output_schema, "InterviewQuestion.v1")
        self.assertIn("interview_answer_104", result.evidence_refs)
        self.assertIn("interview_answer_103", result.evidence_refs)
        self.assertIn("execution_probe_tech_foundation_1", result.evidence_refs)
        call = self.llm.followup_calls[0]
        self.assertEqual(call["role_name"], "Backend Engineer")
        self.assertEqual(call["user_answer"], answer_message.content)
        self.assertEqual(call["history"], recent_history)
        self.assertEqual(call["candidate_profile"], "candidate memory")
        self.assertEqual(call["conversation_summary"], "conversation memory")
        self.assertEqual(call["plan_context"], "plan context")
        self.assertEqual(call["execution_context"], "execution context")
        success = self.recorder.success_calls[0]
        self.assertEqual(success["definition"].owner_agent, "InterviewExecutorAgent")
        self.assertEqual(success["context_refs"]["answer_message_id"], 104)
        self.assertEqual(success["context_refs"]["execution_id"], 30)
        self.assertEqual(
            success["input_snapshot"]["workflow_context"]["step_id"],
            "followup",
        )
        self.assertEqual(
            success["input_snapshot"]["workflow_context"]["workflow_run_id"],
            "interview_runtime_live_1",
        )
        self.assert_contract_ok(success, "InterviewExecutorInputV1", "InterviewQuestionOutputV1")

    async def test_followup_agent_prefers_model_driven_tool_calling_when_runtime_available(self):
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="get_previous_answer",
                description="Retrieve previous answers.",
                handler=lambda context, call: [
                    RetrievedKnowledge(
                        source_name="previous",
                        source_type="interview_message",
                        source_id=1,
                        content=call.query or "",
                    )
                ],
            )
        )
        tool_runtime = ToolRuntime(registry)
        llm = FakeToolCallingLLM()
        agent = InterviewExecutorAgent(
            self.executor,
            self.evidence_builder,
            llm,
            AgentRuntimeConfig(model_name=llm.model),
            tool_runtime=tool_runtime,
        )
        session = SimpleNamespace(
            id=10,
            project_id=1,
            role_name="Backend Engineer",
            interview_plan_id=20,
        )
        answer_message = message(104, "I handled retry and idempotency.", round_no=6)

        result = await agent.run(
            FollowupAgentInput(
                session=session,
                answer_message=answer_message,
                recent_history=[answer_message],
                execution=SimpleNamespace(id=30, current_section_index=0, state={"sections": []}),
                open_threads=[{"status": "open", "highlight": "retry"}],
            )
        )

        self.assertEqual(result.output, "tool-aware followup")
        self.assertEqual(llm.followup_calls[0]["allowed_tool_names"], ("get_previous_answer",))
        self.assertEqual(llm.followup_calls[0]["open_threads"][0]["highlight"], "retry")
        success = self.recorder.success_calls[0]
        self.assertEqual(success["input_snapshot"]["tool_calling_mode"], "model_driven")
        self.assertEqual(success["input_snapshot"]["tool_calls"], [])
        self.assertEqual(
            success["input_snapshot"]["tool_calling_trace"][0]["tool_name"],
            "get_previous_answer",
        )

    async def test_session_memory_agent_generates_candidate_profile_memory(self):
        agent = SessionMemoryAgent(self.executor, self.evidence_builder, self.llm, self.config)
        session = SimpleNamespace(id=10, project_id=1)
        messages = [message(101, "I built a backend retry pipeline.", round_no=3)]

        result = await agent.run(
            SessionMemoryAgentInput(
                prompt_id="candidate_profile",
                session=session,
                session_id=10,
                previous_content="old candidate memory",
                profile_messages=messages,
                previous_summary_id=201,
                workflow_run_id="interview_runtime_live_1",
            )
        )

        self.assertEqual(result.output, "candidate memory")
        self.assertEqual(result.raw_response, {"raw": "candidate_profile"})
        self.assertEqual(result.definition.prompt_id, "candidate_profile")
        self.assertEqual(result.output_schema, "SessionCandidateMemory.v1")
        self.assertEqual(result.message_fields()["content"], "candidate memory")
        self.assertEqual(
            self.llm.candidate_profile_calls,
            [("old candidate memory", messages)],
        )
        self.assertEqual(self.llm.conversation_summary_calls, [])
        self.assertIn("interview_answer_101", result.evidence_refs)
        success = self.recorder.success_calls[0]
        self.assertEqual(success["definition"].owner_agent, "SessionMemoryAgent")
        self.assertEqual(success["context_refs"]["previous_summary_id"], 201)
        self.assertEqual(
            success["input_snapshot"]["workflow_context"]["workflow_run_id"],
            "interview_runtime_live_1",
        )
        self.assert_contract_ok(success, "SessionMemoryInputV1", "SessionMemoryOutputV1")

    async def test_session_memory_agent_generates_conversation_summary(self):
        agent = SessionMemoryAgent(self.executor, self.evidence_builder, self.llm, self.config)
        session = SimpleNamespace(id=10, project_id=1)
        messages = [message(102, "I handled retries and idempotency.", round_no=4)]

        result = await agent.run(
            SessionMemoryAgentInput(
                prompt_id="conversation_summary",
                session=session,
                session_id=10,
                previous_content="old summary",
                profile_messages=messages,
                previous_summary_id=202,
            )
        )

        self.assertEqual(result.output, "conversation memory")
        self.assertEqual(result.raw_response, {"raw": "conversation_summary"})
        self.assertEqual(result.definition.prompt_id, "conversation_summary")
        self.assertEqual(result.output_schema, "ConversationSummary.v1")
        self.assertEqual(self.llm.candidate_profile_calls, [])
        self.assertEqual(
            self.llm.conversation_summary_calls,
            [("old summary", messages)],
        )
        self.assertIn("interview_answer_102", result.evidence_refs)
        success = self.recorder.success_calls[0]
        self.assertEqual(success["definition"].owner_agent, "SessionMemoryAgent")
        self.assertEqual(
            success["input_snapshot"]["workflow_context"]["step_id"],
            "conversation_summary",
        )
        self.assert_contract_ok(success, "SessionMemoryInputV1", "SessionMemoryOutputV1")

    async def test_topic_judge_agent_runs_through_agent_runtime(self):
        agent = TopicJudgeAgent(self.executor, self.evidence_builder, self.llm, self.config)
        session = SimpleNamespace(id=10, project_id=1, interview_plan_id=20)
        execution = SimpleNamespace(
            id=30,
            state={"next_action": {"type": "continue_current_topic"}},
        )
        current_section = {
            "section_key": "tech_foundation",
            "completed_rounds": 1,
            "target_rounds": 2,
            "probe_points": ["Kafka retry", "idempotency"],
            "uncovered_probe_points": ["idempotency"],
        }
        answer_message = message(
            103,
            "I used idempotency keys to avoid duplicate writes.",
            round_no=5,
        )

        result = await agent.run(
            TopicJudgeAgentInput(
                session=session,
                execution=execution,
                current_section=current_section,
                answer_message=answer_message,
                recent_history=[answer_message],
                workflow_run_id="interview_runtime_live_1",
            )
        )

        self.assertEqual(result.output["topic_status"], "complete")
        self.assertEqual(result.raw_response, {"raw": "topic_judge"})
        self.assertEqual(result.definition.prompt_id, "topic_completion_judge")
        self.assertEqual(result.output_schema, "TopicJudgeResult.v1")
        self.assertEqual(
            result.evidence_refs,
            ["interview_answer_103", "topic_probe_tech_foundation_5"],
        )
        call = self.llm.topic_judge_calls[0]
        self.assertEqual(call["current_section"], current_section)
        self.assertEqual(call["execution_state"], execution.state)
        self.assertEqual(call["user_answer"], answer_message.content)
        self.assertEqual(call["recent_history"], [answer_message])
        success = self.recorder.success_calls[0]
        self.assertEqual(success["definition"].owner_agent, "TopicJudgeAgent")
        self.assertEqual(success["context_refs"]["execution_id"], 30)
        self.assertEqual(
            success["input_snapshot"]["workflow_context"]["workflow_run_id"],
            "interview_runtime_live_1",
        )
        self.assert_contract_ok(success, "TopicJudgeInputV1", "TopicJudgeResultV1")

    async def test_topic_judge_agent_prefers_model_driven_tool_calling_when_runtime_available(self):
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="get_previous_answer",
                description="Retrieve previous answers.",
                handler=lambda context, call: [
                    RetrievedKnowledge(
                        source_name="previous",
                        source_type="interview_message",
                        source_id=1,
                        content=call.query or "",
                    )
                ],
            )
        )
        tool_runtime = ToolRuntime(registry)
        llm = FakeToolCallingLLM()
        agent = TopicJudgeAgent(
            self.executor,
            self.evidence_builder,
            llm,
            AgentRuntimeConfig(model_name=llm.model),
            tool_runtime=tool_runtime,
        )
        session = SimpleNamespace(id=10, project_id=1, interview_plan_id=20)
        execution = SimpleNamespace(
            id=30,
            state={"next_action": {"type": "continue_current_topic"}},
        )
        current_section = {
            "section_key": "tech_foundation",
            "completed_rounds": 1,
            "target_rounds": 2,
            "probe_points": ["idempotency", "failure recovery"],
            "uncovered_probe_points": ["failure recovery"],
        }
        answer_message = message(103, "I used idempotency keys.", round_no=5)

        result = await agent.run(
            TopicJudgeAgentInput(
                session=session,
                execution=execution,
                current_section=current_section,
                answer_message=answer_message,
                recent_history=[answer_message],
            )
        )

        self.assertEqual(result.output["topic_status"], "partial")
        self.assertEqual(llm.topic_judge_calls[0]["allowed_tool_names"], ("get_previous_answer",))
        success = self.recorder.success_calls[0]
        self.assertEqual(success["input_snapshot"]["tool_calling_mode"], "model_driven")
        self.assertEqual(success["input_snapshot"]["tool_calls"], [])
        self.assertEqual(
            success["input_snapshot"]["tool_calling_trace"][0]["tool_name"],
            "get_previous_answer",
        )

    async def test_followup_agent_records_input_contract_errors(self):
        agent = InterviewExecutorAgent(self.executor, self.evidence_builder, self.llm, self.config)
        session = SimpleNamespace(
            id=10,
            project_id=1,
            role_name="Backend Engineer",
            interview_plan_id=20,
        )
        answer_message = message(104, "", round_no=6)

        await agent.run(
            FollowupAgentInput(
                session=session,
                answer_message=answer_message,
                recent_history=[answer_message],
                candidate_profile=None,
                conversation_summary=None,
                plan_context=None,
                execution_context=None,
                candidate_profile_id=None,
                conversation_summary_id=None,
                execution=None,
            )
        )

        contract = self.recorder.success_calls[0]["input_snapshot"]["agent_contract_validation"]
        self.assertEqual(contract["input_schema"], "InterviewExecutorInputV1")
        self.assertEqual(contract["output_schema"], "InterviewQuestionOutputV1")
        self.assertFalse(contract["input_ok"])
        self.assertTrue(contract["output_ok"])
        self.assertIn("input.answer_content_length", contract["errors"][0])


if __name__ == "__main__":
    unittest.main()
