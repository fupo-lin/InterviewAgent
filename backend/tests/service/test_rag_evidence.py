import unittest
from types import SimpleNamespace

from service.support import configure_backend_imports

configure_backend_imports()

from app.service.evidence_contract import EvidencePacketValidator
from app.service.evidence_service import EvidencePacketBuilder
from app.service.interview_agent_spec_builder import InterviewAgentSpecBuilder
from app.service.agent_tools import build_interview_tool_planner, build_interview_tool_runtime
from app.service.retrieval_tools import LocalKnowledgeRetriever


class FakeAgentRunExecutor:
    def definition(self, prompt_id):
        return SimpleNamespace(task="followup_generation")

    def spec(self, **kwargs):
        return SimpleNamespace(**kwargs)


class FakeMessageRepo:
    def list_by_session_id(self, session_id):
        return [
            SimpleNamespace(
                id=1,
                session_id=session_id,
                role_type="assistant",
                round_no=1,
                content="question",
            ),
            SimpleNamespace(
                id=2,
                session_id=session_id,
                role_type="user",
                round_no=1,
                content="I used Redis and MySQL to reduce latency.",
            ),
        ]


class FakeArtifactRepo:
    def __init__(self, item):
        self.item = item

    def get_latest_by_project_id(self, project_id):
        return self.item


class RagEvidenceTest(unittest.TestCase):
    def test_retrieval_results_enter_evidence_packet(self):
        builder = EvidencePacketBuilder()
        packet = builder.build_question_generation_packet(
            task="followup_generation",
            session_id=10,
            project_id=20,
            user_answer_message_id=2,
            user_answer="Redis latency",
            round_no=1,
            retrieved_knowledge=[
                SimpleNamespace(
                    source_name="search_technology",
                    source_type="resume_profile",
                    source_id=99,
                    content="Redis cache, MySQL schema optimization",
                    score=1.0,
                    metadata={"tool_name": "search_technology"},
                )
            ],
        )

        validation = EvidencePacketValidator().validate(packet)

        self.assertTrue(validation.ok, validation.errors)
        evidence_types = [item["evidence_type"] for item in packet["evidence_items"]]
        self.assertIn("retrieved_knowledge", evidence_types)

    def test_followup_spec_records_tool_decision_and_rag_evidence(self):
        retriever = LocalKnowledgeRetriever(
            message_repo=FakeMessageRepo(),
            resume_profile_repo=FakeArtifactRepo(
                SimpleNamespace(
                    id=31,
                    resume_id=41,
                    content={"skills": ["Redis", "MySQL"]},
                )
            ),
            jd_analysis_repo=FakeArtifactRepo(None),
            gap_analysis_repo=FakeArtifactRepo(None),
            project_candidate_profile_repo=FakeArtifactRepo(None),
        )
        spec_builder = InterviewAgentSpecBuilder(
            agent_run_executor=FakeAgentRunExecutor(),
            evidence_builder=EvidencePacketBuilder(),
            retriever=retriever,
            tool_runtime=build_interview_tool_runtime(retriever),
            tool_planner=build_interview_tool_planner(),
        )
        session = SimpleNamespace(
            id=10,
            project_id=20,
            role_name="Backend Engineer",
            interview_plan_id=None,
        )
        answer = SimpleNamespace(id=2, content="Redis latency", round_no=1)

        spec = spec_builder.followup(
            session=session,
            answer_message=answer,
            recent_history=[],
        )

        self.assertIn("tool_calls", spec.input_snapshot)
        self.assertIn("tool_results", spec.input_snapshot)
        self.assertIn("get_previous_answer", spec.context_refs["tool_names"])
        self.assertGreater(spec.input_snapshot["retrieved_knowledge_count"], 0)
        self.assertEqual(spec.input_snapshot["tool_results"][0]["status"], "success")
        self.assertTrue(
            any(
                item["evidence_type"] == "retrieved_knowledge"
                for item in spec.evidence_packet["evidence_items"]
            )
        )


if __name__ == "__main__":
    unittest.main()
