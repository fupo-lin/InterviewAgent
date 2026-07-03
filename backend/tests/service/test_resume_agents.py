import unittest
from types import SimpleNamespace

from service.support import configure_backend_imports

configure_backend_imports()

from app.service.agent_run_service import AgentRunExecutor
from app.service.agent_runtime import AgentRuntimeConfig
from app.service.evidence_service import EvidencePacketBuilder
from app.service.project_agent_spec_builder import ProjectAgentContext
from app.service.resume_agents import (
    ResumeAuthenticityAgent,
    ResumeAuthenticityAgentInput,
    ResumeRewriteAgent,
    ResumeRewriteAgentInput,
)


class FakeRecorder:
    def __init__(self) -> None:
        self.success_calls = []

    def record_success(self, **kwargs):
        self.success_calls.append(kwargs)
        return SimpleNamespace(id=700 + len(self.success_calls))

    def record_failure(self, **kwargs):
        raise AssertionError("failure was not expected")


class FakeLLM:
    model = "test-model"

    def __init__(self) -> None:
        self.authenticity_calls = []
        self.rewrite_calls = []

    async def generate_resume_authenticity_report(self, **kwargs):
        self.authenticity_calls.append(kwargs)
        return {
            "overall_authenticity": "medium",
            "claim_checks": [],
            "unsupported_claims": [],
            "strongly_supported_claims": [],
            "rewrite_constraints": [],
            "missing_evidence_to_collect": [],
            "summary": "ok",
        }, {"raw": "authenticity"}

    async def generate_resume_rewrite(self, **kwargs):
        self.rewrite_calls.append(kwargs)
        return {
            "rewrite_mode": kwargs["rewrite_mode"],
            "summary": "ok",
            "rewritten_sections": [],
            "missing_info_to_collect": [],
            "risk_warnings": [],
            "ats_keywords": [],
            "final_suggestions": [],
        }, {"raw": "rewrite"}


def artifact(artifact_id: int, content: dict):
    return SimpleNamespace(id=artifact_id, content=content)


class ResumeAgentRuntimeTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.recorder = FakeRecorder()
        self.executor = AgentRunExecutor(db=SimpleNamespace(), recorder=self.recorder)
        self.evidence_builder = EvidencePacketBuilder()
        self.llm = FakeLLM()
        self.config = AgentRuntimeConfig(model_name=self.llm.model)

    async def test_resume_authenticity_agent_runs_through_agent_runtime(self):
        agent = ResumeAuthenticityAgent(
            agent_run_executor=self.executor,
            evidence_builder=self.evidence_builder,
            llm=self.llm,
            config=self.config,
        )
        context = ProjectAgentContext(
            jd_analysis=artifact(11, {"required_skills": ["Kafka"]}),
            resume_profile=artifact(
                22,
                {
                    "projects": [{"name": "Risk", "summary": "Built risk backend."}],
                    "skills": ["Kafka"],
                },
            ),
            gap_analysis=artifact(33, {"gap_points": []}),
            candidate_profile=artifact(44, {"summary": "Backend candidate"}),
        )

        result = await agent.run(
            ResumeAuthenticityAgentInput(
                project_id=1,
                resume_id=9,
                resume_content="resume text",
                session_id=10,
                execution_state={"sections": []},
                evaluation={"summary": "ok"},
                transcript_messages=[],
                context=context,
            )
        )

        self.assertEqual(result.output["overall_authenticity"], "medium")
        self.assertEqual(result.raw_response, {"raw": "authenticity"})
        self.assertEqual(result.agent_run.id, 701)
        self.assertEqual(result.definition.prompt_id, "resume_authenticity")
        self.assertEqual(result.output_schema, "ResumeAuthenticityReport.v1")
        self.assertEqual(len(self.llm.authenticity_calls), 1)
        call = self.llm.authenticity_calls[0]
        self.assertEqual(call["resume_content"], "resume text")
        self.assertEqual(call["resume_profile"], context.resume_profile.content)
        self.assertEqual(call["project_candidate_profile"], context.candidate_profile.content)
        self.assertEqual(call["evidence_packet"]["task"], "resume_authenticity_check")
        self.assertIn("resume_claim_project_1", result.evidence_refs)
        success = self.recorder.success_calls[0]
        self.assertEqual(success["definition"].owner_agent, "ResumeAuthenticityAgent")
        self.assertEqual(success["model_name"], "test-model")
        contract = success["input_snapshot"]["agent_contract_validation"]
        self.assertEqual(contract["input_schema"], "ResumeAuthenticityInputV1")
        self.assertEqual(contract["output_schema"], "ResumeAuthenticityReportV1")
        self.assertTrue(contract["input_ok"])
        self.assertTrue(contract["output_ok"])
        self.assertEqual(contract["errors"], [])

    async def test_resume_rewrite_agent_runs_through_agent_runtime(self):
        agent = ResumeRewriteAgent(
            agent_run_executor=self.executor,
            evidence_builder=self.evidence_builder,
            llm=self.llm,
            config=self.config,
        )
        context = ProjectAgentContext(
            resume_profile=artifact(
                22,
                {"projects": [{"name": "Risk", "summary": "Built risk backend."}]},
            ),
            candidate_profile=artifact(44, {"summary": "Backend candidate"}),
        )
        resume_authenticity = {
            "claim_checks": [
                {
                    "resume_claim": "Built risk backend",
                    "status": "supported",
                    "evidence": "Explained in interview",
                }
            ]
        }

        result = await agent.run(
            ResumeRewriteAgentInput(
                project_id=1,
                resume_id=9,
                resume_content="resume text",
                rewrite_mode="jd_targeted",
                authenticity_report_id=88,
                resume_authenticity=resume_authenticity,
                execution_state=None,
                evaluation=None,
                transcript_messages=[],
                context=context,
            )
        )

        self.assertEqual(result.output["rewrite_mode"], "jd_targeted")
        self.assertEqual(result.raw_response, {"raw": "rewrite"})
        self.assertEqual(result.definition.prompt_id, "resume_rewrite")
        self.assertEqual(result.output_schema, "ResumeRewriteResult.v1")
        self.assertEqual(len(self.llm.rewrite_calls), 1)
        call = self.llm.rewrite_calls[0]
        self.assertEqual(call["rewrite_mode"], "jd_targeted")
        self.assertEqual(call["resume_content"], "resume text")
        self.assertEqual(call["resume_authenticity"], resume_authenticity)
        self.assertEqual(call["evidence_packet"]["task"], "resume_rewrite")
        self.assertIn("authenticity_check_1", result.evidence_refs)
        success = self.recorder.success_calls[0]
        self.assertEqual(success["definition"].owner_agent, "ResumeRewriteAgent")
        self.assertEqual(success["context_refs"]["authenticity_report_id"], 88)
        contract = success["input_snapshot"]["agent_contract_validation"]
        self.assertEqual(contract["input_schema"], "ResumeRewriteInputV1")
        self.assertEqual(contract["output_schema"], "ResumeRewriteResultV1")
        self.assertTrue(contract["input_ok"])
        self.assertTrue(contract["output_ok"])
        self.assertEqual(contract["errors"], [])

    async def test_resume_authenticity_agent_records_input_contract_errors(self):
        agent = ResumeAuthenticityAgent(
            agent_run_executor=self.executor,
            evidence_builder=self.evidence_builder,
            llm=self.llm,
            config=self.config,
        )
        context = ProjectAgentContext()

        await agent.run(
            ResumeAuthenticityAgentInput(
                project_id=1,
                resume_id=9,
                resume_content="",
                session_id=None,
                execution_state=None,
                evaluation=None,
                transcript_messages=[],
                context=context,
            )
        )

        contract = self.recorder.success_calls[0]["input_snapshot"]["agent_contract_validation"]
        self.assertFalse(contract["input_ok"])
        self.assertTrue(contract["output_ok"])
        self.assertIn("input.resume_content", contract["errors"][0])


if __name__ == "__main__":
    unittest.main()
