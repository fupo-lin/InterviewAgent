import unittest
from types import SimpleNamespace

from service.support import configure_backend_imports

configure_backend_imports()

from app.service.agent_run_service import AgentRunExecutor
from app.service.evidence_service import EvidencePacketBuilder
from app.service.interview_agent_spec_builder import InterviewAgentSpecBuilder


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
        round_no=round_no,
        content=content,
    )


class InterviewAgentSpecBuilderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.executor = AgentRunExecutor(db=None)
        self.builder = InterviewAgentSpecBuilder(
            agent_run_executor=self.executor,
            evidence_builder=EvidencePacketBuilder(),
        )

    def test_followup_spec_uses_answer_history_and_execution_evidence(self):
        session = SimpleNamespace(
            id=10,
            project_id=1,
            role_name="Backend Engineer",
            interview_plan_id=20,
        )
        answer_message = message(
            message_id=101,
            session_id=10,
            round_no=3,
            content="I used Kafka retries and idempotency keys.",
        )
        recent_history = [
            message(message_id=99, session_id=10, round_no=2, content="Previous answer"),
            SimpleNamespace(
                id=100,
                session_id=10,
                role_type="assistant",
                round_no=3,
                content="Please explain reliability.",
            ),
        ]
        execution = SimpleNamespace(
            id=30,
            state={
                "sections": [
                    {
                        "section_key": "tech_foundation",
                        "evidence": [
                            {
                                "round_no": 2,
                                "answer_excerpt": "Discussed retries.",
                                "covered_probe_points": ["Kafka retry"],
                                "confidence": "medium",
                            }
                        ],
                    }
                ]
            },
        )

        spec = self.builder.followup(
            session=session,
            answer_message=answer_message,
            recent_history=recent_history,
            candidate_profile="Strong backend profile",
            conversation_summary="Discussed distributed systems",
            plan_context="Ask reliability questions",
            execution_context="Current section tech foundation",
            candidate_profile_id=201,
            conversation_summary_id=202,
            execution=execution,
            workflow_run_id="interview_runtime_live_1",
        )
        run_context = self.executor.context_from_spec(spec)

        self.assertEqual(spec.prompt_id, "followup")
        self.assertEqual(spec.project_id, 1)
        self.assertEqual(spec.session_id, 10)
        self.assertEqual(spec.input_snapshot["role_name"], "Backend Engineer")
        self.assertEqual(spec.input_snapshot["answer_message_id"], 101)
        self.assertEqual(spec.input_snapshot["round_no"], 3)
        self.assertEqual(spec.input_snapshot["recent_history_count"], 2)
        self.assertTrue(spec.input_snapshot["has_candidate_profile"])
        self.assertTrue(spec.input_snapshot["has_execution_context"])
        self.assertEqual(spec.context_refs["candidate_profile_summary_id"], 201)
        self.assertEqual(spec.context_refs["conversation_summary_id"], 202)
        self.assertEqual(spec.context_refs["interview_plan_id"], 20)
        self.assertEqual(spec.context_refs["execution_id"], 30)
        self.assertEqual(spec.workflow_context["workflow_id"], "interview_runtime")
        self.assertEqual(spec.workflow_context["workflow_run_id"], "interview_runtime_live_1")
        self.assertEqual(spec.workflow_context["step_id"], "followup")
        self.assertEqual(spec.evidence_packet["task"], "followup_generation")
        self.assertIn("interview_answer_101", run_context.evidence_refs)
        self.assertIn("interview_answer_99", run_context.evidence_refs)
        self.assertIn("execution_probe_tech_foundation_1", run_context.evidence_refs)
        self.assertEqual(spec.output_snapshot("next question"), {"reply": "next question"})

    def test_topic_judge_spec_locks_section_refs_and_required_evidence(self):
        session = SimpleNamespace(id=10, project_id=1, interview_plan_id=20)
        execution = SimpleNamespace(
            id=30,
            state={"next_action": {"type": "continue_section"}},
        )
        current_section = {
            "section_key": "tech_foundation",
            "completed_rounds": 1,
            "target_rounds": 2,
            "probe_points": ["Kafka retry"],
            "uncovered_probe_points": ["idempotency"],
        }
        answer_message = message(
            message_id=102,
            session_id=10,
            round_no=4,
            content="I added idempotency keys to avoid duplicate writes.",
        )

        spec = self.builder.topic_judge(
            session=session,
            execution=execution,
            current_section=current_section,
            answer_message=answer_message,
            recent_history=[answer_message],
            workflow_run_id="interview_runtime_live_1",
        )
        run_context = self.executor.context_from_spec(spec)

        self.assertEqual(spec.prompt_id, "topic_completion_judge")
        self.assertEqual(spec.input_snapshot["current_section_key"], "tech_foundation")
        self.assertEqual(spec.input_snapshot["current_section_completed_rounds"], 1)
        self.assertEqual(spec.input_snapshot["current_section_target_rounds"], 2)
        self.assertEqual(spec.input_snapshot["recent_history_count"], 1)
        self.assertEqual(spec.context_refs["interview_plan_id"], 20)
        self.assertEqual(spec.context_refs["execution_id"], 30)
        self.assertEqual(spec.context_refs["answer_message_id"], 102)
        self.assertEqual(spec.context_refs["current_section_key"], "tech_foundation")
        self.assertEqual(spec.workflow_context["workflow_id"], "interview_runtime")
        self.assertEqual(spec.workflow_context["workflow_run_id"], "interview_runtime_live_1")
        self.assertEqual(spec.workflow_context["step_id"], "topic_completion_judge")
        self.assertEqual(spec.evidence_packet["task"], "topic_completion_judge")
        self.assertEqual(spec.evidence_packet["missing_evidence"], [])
        self.assertEqual(
            run_context.evidence_refs,
            ["interview_answer_102", "topic_probe_tech_foundation_4"],
        )

    def test_runtime_specs_keep_session_workflow_run_id_when_not_overridden(self):
        session = SimpleNamespace(
            id=10,
            project_id=1,
            role_name="Backend Engineer",
            interview_plan_id=20,
        )
        answer_message = message(
            message_id=101,
            session_id=10,
            round_no=3,
            content="I used retries.",
        )

        spec = self.builder.followup(
            session=session,
            answer_message=answer_message,
            recent_history=[],
        )

        self.assertEqual(spec.workflow_context["workflow_run_id"], "session_10_interview_runtime")


if __name__ == "__main__":
    unittest.main()
