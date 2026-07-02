import unittest
from types import SimpleNamespace

from service.support import configure_backend_imports

configure_backend_imports()

from app.service.agent_run_service import AgentRunExecutor
from app.service.agent_runtime import AgentRuntimeConfig
from app.service.assessment_agents import (
    EvaluationAgent,
    EvaluationAgentInput,
    ProjectCandidateProfileAgent,
    ProjectCandidateProfileAgentInput,
)
from app.service.evidence_service import EvidencePacketBuilder
from app.service.project_agent_spec_builder import ProjectAgentContext


class FakeRecorder:
    def __init__(self) -> None:
        self.success_calls = []

    def record_success(self, **kwargs):
        self.success_calls.append(kwargs)
        return SimpleNamespace(id=800 + len(self.success_calls))

    def record_failure(self, **kwargs):
        raise AssertionError("failure was not expected")


class FakeLLM:
    model = "test-model"

    def __init__(self) -> None:
        self.evaluation_calls = []
        self.project_profile_calls = []

    async def generate_evaluation(self, *args, **kwargs):
        self.evaluation_calls.append((args, kwargs))
        return {
            "strengths": "clear project context",
            "weaknesses": "needs metrics",
            "suggestions": "prepare numbers",
            "summary": "ok",
            "technical_ability": "medium",
            "project_experience": "medium",
            "communication": "clear",
            "improvement_suggestions": "prepare numbers",
        }, {"raw": "evaluation"}

    async def generate_project_candidate_profile(self, **kwargs):
        self.project_profile_calls.append(kwargs)
        return {
            "basic_profile": {"target_role": kwargs["target_role"]},
            "project_experience": [],
            "capability_profile": {},
            "risk_profile": [],
            "learning_needs": [],
            "resume_optimization_focus": [],
            "summary": "project profile",
        }, {"raw": "project_profile"}


def message(message_id: int, role_type: str, content: str, round_no: int = 1):
    return SimpleNamespace(
        id=message_id,
        session_id=10,
        role_type=role_type,
        message_type="answer" if role_type == "user" else "question",
        round_no=round_no,
        content=content,
    )


def artifact(artifact_id: int, content):
    return SimpleNamespace(id=artifact_id, content=content)


class AssessmentAgentRuntimeTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.recorder = FakeRecorder()
        self.executor = AgentRunExecutor(db=SimpleNamespace(), recorder=self.recorder)
        self.evidence_builder = EvidencePacketBuilder()
        self.llm = FakeLLM()
        self.config = AgentRuntimeConfig(model_name=self.llm.model)

    async def test_evaluation_agent_runs_through_agent_runtime(self):
        agent = EvaluationAgent(
            agent_run_executor=self.executor,
            evidence_builder=self.evidence_builder,
            llm=self.llm,
            config=self.config,
        )
        session = SimpleNamespace(id=10, project_id=1, interview_plan_id=20)
        history = [
            message(1, "assistant", "Please introduce your project."),
            message(2, "user", "I built a backend service with retry handling."),
        ]
        execution = SimpleNamespace(
            id=30,
            state={
                "sections": [
                    {
                        "section_key": "project_depth",
                        "evidence": [
                            {
                                "round_no": 1,
                                "answer_excerpt": "retry handling",
                                "probe_point": "technical depth",
                            }
                        ],
                    }
                ]
            },
        )
        candidate_profile = artifact(40, "candidate memory")
        conversation_summary = artifact(41, "conversation memory")

        result = await agent.run(
            EvaluationAgentInput(
                session=session,
                history=history,
                full_history=history,
                execution=execution,
                candidate_profile=candidate_profile,
                conversation_summary=conversation_summary,
                plan_context="plan context",
            )
        )

        self.assertEqual(result.output["summary"], "ok")
        self.assertEqual(result.raw_response, {"raw": "evaluation"})
        self.assertEqual(result.agent_run.id, 801)
        self.assertEqual(result.definition.prompt_id, "evaluation")
        self.assertEqual(result.output_schema, "InterviewEvaluation.v1")
        self.assertIn("interview_answer_2", result.evidence_refs)
        self.assertIn("execution_probe_project_depth_1", result.evidence_refs)
        args, kwargs = self.llm.evaluation_calls[0]
        self.assertEqual(args[0], history)
        self.assertEqual(kwargs["candidate_profile"], "candidate memory")
        self.assertEqual(kwargs["conversation_summary"], "conversation memory")
        self.assertEqual(kwargs["plan_context"], "plan context")
        self.assertEqual(kwargs["evidence_packet"]["task"], "evaluation_generation")
        success = self.recorder.success_calls[0]
        self.assertEqual(success["definition"].owner_agent, "EvaluationAgent")
        self.assertEqual(success["context_refs"]["execution_id"], 30)
        contract = success["input_snapshot"]["agent_contract_validation"]
        self.assertEqual(contract["input_schema"], "EvaluationInputV1")
        self.assertEqual(contract["output_schema"], "InterviewEvaluationV1")
        self.assertTrue(contract["input_ok"])
        self.assertTrue(contract["output_ok"])
        self.assertEqual(contract["errors"], [])

    async def test_project_candidate_profile_agent_runs_through_agent_runtime(self):
        agent = ProjectCandidateProfileAgent(
            agent_run_executor=self.executor,
            evidence_builder=self.evidence_builder,
            llm=self.llm,
            config=self.config,
        )
        context = ProjectAgentContext(
            jd_analysis=artifact(11, {"required_skills": ["FastAPI"]}),
            resume_profile=artifact(
                22,
                {
                    "projects": [{"name": "Interview", "summary": "Built interview backend."}],
                    "skills": ["FastAPI"],
                },
            ),
            gap_analysis=artifact(33, {"gap_points": []}),
        )
        transcript = [message(2, "user", "I owned the backend API.", round_no=2)]

        result = await agent.run(
            ProjectCandidateProfileAgentInput(
                project_id=1,
                target_role="Backend Engineer",
                source_session_id=10,
                execution_state={"sections": []},
                evaluation={"summary": "ok"},
                transcript_messages=transcript,
                context=context,
            )
        )

        self.assertEqual(result.output["summary"], "project profile")
        self.assertEqual(result.raw_response, {"raw": "project_profile"})
        self.assertEqual(result.definition.prompt_id, "project_candidate_profile")
        self.assertEqual(result.output_schema, "ProjectCandidateProfile.v1")
        self.assertIn("resume_claim_project_1", result.evidence_refs)
        self.assertIn("interview_answer_2", result.evidence_refs)
        call = self.llm.project_profile_calls[0]
        self.assertEqual(call["target_role"], "Backend Engineer")
        self.assertEqual(call["jd_analysis"], context.jd_analysis.content)
        self.assertEqual(call["resume_profile"], context.resume_profile.content)
        self.assertEqual(call["gap_analysis"], context.gap_analysis.content)
        self.assertEqual(call["evaluation"], {"summary": "ok"})
        self.assertEqual(call["evidence_packet"]["task"], "project_candidate_profile")
        success = self.recorder.success_calls[0]
        self.assertEqual(success["definition"].owner_agent, "ProjectCandidateProfileAgent")
        self.assertEqual(success["context_refs"]["source_session_id"], 10)
        contract = success["input_snapshot"]["agent_contract_validation"]
        self.assertEqual(contract["input_schema"], "ProjectCandidateProfileInputV1")
        self.assertEqual(contract["output_schema"], "ProjectCandidateProfileV1")
        self.assertTrue(contract["input_ok"])
        self.assertTrue(contract["output_ok"])
        self.assertEqual(contract["errors"], [])

    async def test_project_candidate_profile_agent_records_input_contract_errors(self):
        agent = ProjectCandidateProfileAgent(
            agent_run_executor=self.executor,
            evidence_builder=self.evidence_builder,
            llm=self.llm,
            config=self.config,
        )

        await agent.run(
            ProjectCandidateProfileAgentInput(
                project_id=0,
                target_role="Backend Engineer",
                source_session_id=None,
                execution_state=None,
                evaluation=None,
                transcript_messages=[],
                context=ProjectAgentContext(),
            )
        )

        contract = self.recorder.success_calls[0]["input_snapshot"]["agent_contract_validation"]
        self.assertFalse(contract["input_ok"])
        self.assertTrue(contract["output_ok"])
        self.assertIn("input.project_id", contract["errors"][0])


if __name__ == "__main__":
    unittest.main()
