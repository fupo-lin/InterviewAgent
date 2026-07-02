import unittest
from types import SimpleNamespace

from service.support import configure_backend_imports

configure_backend_imports()

from app.service.agent_run_service import AgentRunExecutor
from app.service.agent_runtime import AgentRuntimeConfig
from app.service.evidence_service import EvidencePacketBuilder
from app.service.preparation_agents import (
    GapAnalysisAgent,
    GapAnalysisAgentInput,
    InterviewPlanAgent,
    InterviewPlanAgentInput,
    JDAnalysisAgent,
    JDAnalysisAgentInput,
    ResumeAnalysisAgent,
    ResumeAnalysisAgentInput,
)


class FakeRecorder:
    def __init__(self) -> None:
        self.success_calls = []

    def record_success(self, **kwargs):
        self.success_calls.append(kwargs)
        return SimpleNamespace(id=900 + len(self.success_calls))

    def record_failure(self, **kwargs):
        raise AssertionError("failure was not expected")


class FakeLLM:
    model = "test-model"

    def __init__(self) -> None:
        self.jd_calls = []
        self.resume_calls = []
        self.gap_calls = []
        self.plan_calls = []

    async def generate_jd_analysis(self, jd_content: str):
        self.jd_calls.append(jd_content)
        return {"required_skills": ["Python"]}, {"raw": "jd"}

    async def generate_resume_profile(self, resume_content: str):
        self.resume_calls.append(resume_content)
        return {"projects": [{"summary": "Built backend"}]}, {"raw": "resume"}

    async def generate_gap_analysis(self, jd_analysis: dict, resume_profile: dict):
        self.gap_calls.append((jd_analysis, resume_profile))
        return {"gap_points": []}, {"raw": "gap"}

    async def generate_interview_plan(self, **kwargs):
        self.plan_calls.append(kwargs)
        return {"plan_mode": kwargs["plan_mode"], "sections": []}, {"raw": "plan"}


def artifact(artifact_id: int, content: dict, **extra):
    values = {
        "id": artifact_id,
        "content": content,
        "agent_run_id": extra.pop("agent_run_id", 100 + artifact_id),
        "evidence_refs": extra.pop("evidence_refs", []),
        "schema_version": extra.pop("schema_version", "TestSchema.v1"),
    }
    values.update(extra)
    return SimpleNamespace(**values)


class PreparationAgentRuntimeTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.recorder = FakeRecorder()
        self.executor = AgentRunExecutor(db=SimpleNamespace(), recorder=self.recorder)
        self.evidence_builder = EvidencePacketBuilder()
        self.llm = FakeLLM()
        self.config = AgentRuntimeConfig(model_name=self.llm.model)

    async def test_jd_analysis_agent_runs_through_agent_runtime(self):
        agent = JDAnalysisAgent(self.executor, self.evidence_builder, self.llm, self.config)
        jd = SimpleNamespace(
            id=11,
            raw_content="Backend engineer JD",
            title="Backend Engineer",
            company_name="Acme",
            source_url="https://example.test/jd",
        )

        result = await agent.run(JDAnalysisAgentInput(project_id=1, jd=jd))

        self.assertEqual(result.output, {"required_skills": ["Python"]})
        self.assertEqual(result.raw_response, {"raw": "jd"})
        self.assertEqual(result.definition.prompt_id, "jd_analysis")
        self.assertEqual(result.output_schema, "JDAnalysis.v1")
        self.assertEqual(self.llm.jd_calls, ["Backend engineer JD"])
        self.assertIn("jd_requirement_11", result.evidence_refs)
        self.assertEqual(self.recorder.success_calls[0]["definition"].owner_agent, "JDAnalysisAgent")

    async def test_resume_analysis_agent_runs_through_agent_runtime(self):
        agent = ResumeAnalysisAgent(self.executor, self.evidence_builder, self.llm, self.config)
        resume = SimpleNamespace(
            id=12,
            raw_content="Built backend services",
            file_name="resume.txt",
            file_type="txt",
        )

        result = await agent.run(ResumeAnalysisAgentInput(project_id=1, resume=resume))

        self.assertEqual(result.output, {"projects": [{"summary": "Built backend"}]})
        self.assertEqual(result.raw_response, {"raw": "resume"})
        self.assertEqual(result.definition.prompt_id, "resume_analysis")
        self.assertEqual(result.output_schema, "ResumeProfile.v1")
        self.assertEqual(self.llm.resume_calls, ["Built backend services"])
        self.assertIn("resume_claim_12", result.evidence_refs)
        self.assertEqual(self.recorder.success_calls[0]["definition"].owner_agent, "ResumeAnalysisAgent")

    async def test_gap_analysis_agent_runs_through_agent_runtime(self):
        agent = GapAnalysisAgent(self.executor, self.evidence_builder, self.llm, self.config)
        jd_analysis = artifact(
            21,
            {"required_skills": ["Python"], "core_responsibilities": ["Build APIs"]},
            evidence_refs=["jd_requirement_21"],
            schema_version="JDAnalysis.v1",
        )
        resume_profile = artifact(
            22,
            {"projects": [{"summary": "Built APIs"}], "skills": ["Python"]},
            evidence_refs=["resume_claim_22"],
            schema_version="ResumeProfile.v1",
        )

        result = await agent.run(
            GapAnalysisAgentInput(
                project_id=1,
                jd_analysis=jd_analysis,
                resume_profile=resume_profile,
            )
        )

        self.assertEqual(result.output, {"gap_points": []})
        self.assertEqual(result.raw_response, {"raw": "gap"})
        self.assertEqual(result.definition.prompt_id, "gap_analysis")
        self.assertEqual(result.output_schema, "GapAnalysis.v1")
        self.assertEqual(self.llm.gap_calls, [(jd_analysis.content, resume_profile.content)])
        self.assertIn("jd_analysis_21_required_skills_1", result.evidence_refs)
        self.assertIn("resume_profile_22_resume_claim_project_1", result.evidence_refs)
        success = self.recorder.success_calls[0]
        self.assertEqual(success["definition"].owner_agent, "GapAnalysisAgent")
        self.assertEqual(success["context_refs"]["jd_analysis_id"], 21)
        self.assertEqual(success["context_refs"]["resume_profile_id"], 22)

    async def test_interview_plan_agent_runs_through_agent_runtime(self):
        agent = InterviewPlanAgent(self.executor, self.evidence_builder, self.llm, self.config)
        jd_analysis = artifact(21, {"required_skills": ["Python"]})
        resume_profile = artifact(22, {"projects": [{"summary": "Built APIs"}]})
        gap_analysis = artifact(23, {"gap_points": [{"jd_requirement": "Python"}]})

        result = await agent.run(
            InterviewPlanAgentInput(
                project_id=1,
                target_role="Backend Engineer",
                plan_mode="jd_resume",
                jd_analysis=jd_analysis,
                resume_profile=resume_profile,
                gap_analysis=gap_analysis,
            )
        )

        self.assertEqual(result.output, {"plan_mode": "jd_resume", "sections": []})
        self.assertEqual(result.raw_response, {"raw": "plan"})
        self.assertEqual(result.definition.prompt_id, "interview_plan")
        self.assertEqual(result.output_schema, "InterviewPlan.v1")
        call = self.llm.plan_calls[0]
        self.assertEqual(call["plan_mode"], "jd_resume")
        self.assertEqual(call["target_role"], "Backend Engineer")
        self.assertEqual(call["jd_analysis"], jd_analysis.content)
        self.assertEqual(call["resume_profile"], resume_profile.content)
        self.assertEqual(call["gap_analysis"], gap_analysis.content)
        self.assertIn("jd_analysis_21_required_skills_1", result.evidence_refs)
        self.assertIn("resume_profile_22_resume_claim_project_1", result.evidence_refs)
        success = self.recorder.success_calls[0]
        self.assertEqual(success["definition"].owner_agent, "InterviewPlanAgent")
        self.assertEqual(success["context_refs"]["gap_analysis_id"], 23)


if __name__ == "__main__":
    unittest.main()
