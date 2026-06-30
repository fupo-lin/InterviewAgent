import unittest
from types import SimpleNamespace

from service.support import configure_backend_imports

configure_backend_imports()

from app.service.agent_run_service import AgentRunExecutor
from app.service.evidence_service import EvidencePacketBuilder
from app.service.project_agent_spec_builder import ProjectAgentContext, ProjectAgentSpecBuilder


def artifact(
    artifact_id: int,
    content: dict,
    agent_run_id: int = 100,
    evidence_refs: list[str] | None = None,
    schema_version: str = "TestSchema.v1",
):
    return SimpleNamespace(
        id=artifact_id,
        content=content,
        agent_run_id=agent_run_id,
        evidence_refs=evidence_refs or [],
        schema_version=schema_version,
    )


class ProjectAgentSpecBuilderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.executor = AgentRunExecutor(db=None)
        self.builder = ProjectAgentSpecBuilder(
            agent_run_executor=self.executor,
            evidence_builder=EvidencePacketBuilder(),
        )

    def test_gap_analysis_spec_preserves_source_refs_and_evidence(self):
        jd_analysis = artifact(
            artifact_id=11,
            content={
                "required_skills": ["Python", "MySQL"],
                "core_responsibilities": ["Build backend APIs"],
            },
            agent_run_id=501,
            evidence_refs=["jd_requirement_11"],
            schema_version="JDAnalysis.v1",
        )
        resume_profile = artifact(
            artifact_id=22,
            content={
                "projects": [
                    {
                        "name": "Interview Platform",
                        "summary": "Built FastAPI interview workflow.",
                        "highlights": ["Added async LLM calls"],
                    }
                ],
                "skills": ["Python"],
            },
            agent_run_id=502,
            evidence_refs=["resume_claim_22"],
            schema_version="ResumeProfile.v1",
        )

        spec = self.builder.gap_analysis(
            project_id=1,
            jd_analysis=jd_analysis,
            resume_profile=resume_profile,
        )
        context = self.executor.context_from_spec(spec)

        self.assertEqual(spec.prompt_id, "gap_analysis")
        self.assertEqual(spec.project_id, 1)
        self.assertIsNone(spec.session_id)
        self.assertEqual(spec.input_snapshot["jd_analysis_id"], 11)
        self.assertEqual(spec.input_snapshot["resume_profile_id"], 22)
        self.assertEqual(spec.input_snapshot["jd_analysis_schema_version"], "JDAnalysis.v1")
        self.assertEqual(spec.input_snapshot["resume_profile_schema_version"], "ResumeProfile.v1")
        self.assertEqual(spec.context_refs["jd_analysis_agent_run_id"], 501)
        self.assertEqual(spec.context_refs["resume_profile_agent_run_id"], 502)
        self.assertEqual(spec.context_refs["jd_analysis_evidence_refs"], ["jd_requirement_11"])
        self.assertEqual(spec.context_refs["resume_profile_evidence_refs"], ["resume_claim_22"])
        self.assertEqual(spec.evidence_packet["task"], "gap_analysis")
        self.assertEqual(
            {item["evidence_type"] for item in spec.evidence_packet["evidence_items"]},
            {"jd_requirement", "resume_claim"},
        )
        self.assertIn("evidence_packet", context.input_snapshot)
        self.assertEqual(
            context.evidence_refs,
            [item["evidence_id"] for item in spec.evidence_packet["evidence_items"]],
        )

    def test_resume_rewrite_spec_includes_authenticity_and_resume_evidence(self):
        resume_profile = artifact(
            artifact_id=31,
            content={
                "projects": [{"name": "Risk Control", "summary": "Owned feature rollout."}],
                "skills": [{"name": "Kafka", "evidence": "Built retry pipeline"}],
            },
        )
        candidate_profile = artifact(artifact_id=41, content={"strengths": ["backend"]})
        context = ProjectAgentContext(
            resume_profile=resume_profile,
            candidate_profile=candidate_profile,
        )
        authenticity_report = {
            "claim_checks": [
                {
                    "resume_claim": "Owned feature rollout",
                    "status": "supported",
                    "evidence": "Explained rollout metrics in interview",
                }
            ]
        }

        spec = self.builder.resume_rewrite(
            project_id=2,
            resume_id=7,
            rewrite_mode="jd_targeted",
            authenticity_report_id=88,
            resume_authenticity=authenticity_report,
            execution_state=None,
            transcript_messages=[],
            context=context,
        )
        run_context = self.executor.context_from_spec(spec)

        self.assertEqual(spec.prompt_id, "resume_rewrite")
        self.assertEqual(spec.input_snapshot["resume_id"], 7)
        self.assertEqual(spec.input_snapshot["rewrite_mode"], "jd_targeted")
        self.assertEqual(spec.input_snapshot["authenticity_report_id"], 88)
        self.assertTrue(spec.input_snapshot["has_resume_profile"])
        self.assertTrue(spec.input_snapshot["has_project_candidate_profile"])
        self.assertEqual(spec.context_refs["resume_profile_id"], 31)
        self.assertEqual(spec.context_refs["project_candidate_profile_id"], 41)
        self.assertEqual(spec.context_refs["authenticity_report_id"], 88)
        self.assertEqual(spec.evidence_packet["task"], "resume_rewrite")
        self.assertIn("authenticity_check_1", run_context.evidence_refs)
        self.assertIn("resume_claim_project_1", run_context.evidence_refs)
        self.assertIn("resume_claim_skill_1", run_context.evidence_refs)


if __name__ == "__main__":
    unittest.main()
