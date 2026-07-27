import unittest
from types import SimpleNamespace

from service.support import configure_backend_imports

configure_backend_imports()

from app.service.candidate_growth_report_nodes import CandidateGrowthReportNodes
from app.service.candidate_growth_report_workflow import CandidateGrowthReportWorkflow
from app.schemas.agent_contract import AgentContractValidation
from app.service.agent_runtime import AgentOutputValidationError


def message(message_id: int, role_type: str, content: str, round_no: int = 1):
    return SimpleNamespace(
        id=message_id,
        session_id=10,
        role_type=role_type,
        message_type="answer" if role_type == "user" else "question",
        round_no=round_no,
        content=content,
        status="normal",
    )


def evaluation(evaluation_id: int = 900):
    return SimpleNamespace(
        id=evaluation_id,
        session_id=10,
        strengths="clear project context",
        weaknesses="needs metrics",
        suggestions="prepare numbers",
        summary="ok",
        technical_ability="medium",
        project_experience="medium",
        communication="clear",
        improvement_suggestions="prepare numbers",
        agent_run_id=801,
        schema_version="InterviewEvaluation.v1",
        evidence_refs=["interview_answer_2"],
    )


def report(report_id: int = 700, agent_run_id: int | None = 888):
    return SimpleNamespace(
        id=report_id,
        report_uid=f"report-{report_id}",
        session_id=10,
        project_id=1,
        workflow_run_id="growth-run-1",
        agent_run_id=agent_run_id,
        schema_version="CandidateGrowthReport.v1",
        report_version="v1",
        content={"report_version": "v1", "overall_summary": {"level": "medium"}},
        raw_response={"raw": "report"},
        evidence_refs=["interview_answer_2"],
        status="success",
    )


class FakeMessageRepo:
    def __init__(self) -> None:
        self.messages = [
            message(1, "assistant", "Please introduce your project."),
            message(2, "user", "I built retry handling.", round_no=2),
        ]

    def list_by_session_id(self, session_id):
        return self.messages


class NoAnswerMessageRepo(FakeMessageRepo):
    def __init__(self) -> None:
        self.messages = [message(1, "assistant", "Please introduce your project.")]


class FakeExecutionRepo:
    def get_latest_by_session_id(self, session_id):
        return SimpleNamespace(
            id=40,
            state={"sections": [{"section_key": "system_design", "evidence": []}]},
            status="finished",
        )


_DEFAULT_EVALUATION = object()


class FakeEvaluationRepo:
    def __init__(self, existing=_DEFAULT_EVALUATION) -> None:
        self.existing = evaluation() if existing is _DEFAULT_EVALUATION else existing

    def get_latest_by_session_id(self, session_id):
        return self.existing


class FakeProjectRepo:
    def __init__(self, item=None) -> None:
        self.item = item

    def get_latest_by_project_id(self, project_id):
        return self.item


class FakeGrowthReportRepo:
    def __init__(self, existing=None) -> None:
        self.existing = existing
        self.created = []

    def get_latest_by_session_id(self, session_id, report_version="v1"):
        return self.existing

    def create(self, **kwargs):
        item = report(700 + len(self.created), kwargs.get("agent_run_id"))
        for key, value in kwargs.items():
            setattr(item, key, value)
        self.created.append(item)
        self.existing = item
        return item


class FakeEvidenceBuilder:
    def build_growth_report_packet(self, **kwargs):
        return {
            "packet_id": "growth-packet-1",
            "task": "candidate_growth_report_generation",
            "project_id": kwargs.get("project_id"),
            "session_id": kwargs.get("session_id"),
            "evidence_items": [
                {
                    "evidence_id": "interview_answer_2",
                    "evidence_type": "interview_answer",
                    "source_type": "interview_message",
                    "source_id": 2,
                    "content_excerpt": "I built retry handling.",
                },
                {
                    "evidence_id": "evaluation_900_summary",
                    "evidence_type": "evaluation_finding",
                    "source_type": "interview_evaluation",
                    "source_id": 900,
                    "content_excerpt": "ok",
                },
            ],
            "missing_evidence": [],
        }


class FakeWorkflowRuntime:
    def __init__(self) -> None:
        self.repository = self
        self.run_obj = None
        self.saved = []

    def load_or_create(self, **kwargs):
        if self.run_obj:
            return self.run_obj
        self.run_obj = SimpleNamespace(
            workflow_run_id="growth-run-1",
            workflow_id=kwargs["workflow_id"],
            thread_id=kwargs["thread_id"],
            project_id=kwargs["project_id"],
            session_id=kwargs["session_id"],
            status="running",
            current_step="start",
            state=kwargs["initial_state"],
        )
        return self.run_obj

    def save(self, workflow_run, **kwargs):
        for key, value in kwargs.items():
            setattr(workflow_run, key, value)
        self.saved.append((workflow_run, kwargs))
        return workflow_run


class FakeGrowthReportAgent:
    def __init__(self) -> None:
        self.calls = []

    async def run(self, agent_input):
        self.calls.append(agent_input)
        return SimpleNamespace(
            output={
                "report_version": "v1",
                "overall_summary": {"level": "medium", "summary": "ok"},
                "job_match": {"level": "unknown"},
                "technical_strengths": [],
                "technical_gaps": [],
                "project_storytelling": {},
                "authenticity_risks": [],
                "resume_suggestions": [],
                "next_interview_focus": [],
                "learning_plan": [],
                "evidence_references": [],
            },
            raw_response={"raw": "growth"},
            agent_run=SimpleNamespace(id=888),
            output_schema="CandidateGrowthReport.v1",
            evidence_refs=["interview_answer_2", "evaluation_900_summary"],
        )


class FailingGrowthReportAgent:
    async def run(self, agent_input):
        raise RuntimeError("growth unavailable")


class InvalidOutputGrowthReportAgent:
    async def run(self, agent_input):
        validation = AgentContractValidation(
            output_schema="CandidateGrowthReportV1",
            output_ok=False,
            errors=["output.overall_summary: Input should be a valid dictionary"],
        )
        raise AgentOutputValidationError(validation)


class CandidateGrowthReportWorkflowTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.session = SimpleNamespace(
            id=10,
            session_uid="session-uid",
            project_id=1,
            role_name="Backend Engineer",
            status="finished",
        )
        self.message_repo = FakeMessageRepo()
        self.execution_repo = FakeExecutionRepo()
        self.evaluation_repo = FakeEvaluationRepo()
        self.growth_report_repo = FakeGrowthReportRepo()
        self.growth_report_agent = FakeGrowthReportAgent()
        self.runtime = FakeWorkflowRuntime()
        self.nodes = CandidateGrowthReportNodes(
            message_repo=self.message_repo,
            execution_repo=self.execution_repo,
            evaluation_repo=self.evaluation_repo,
            growth_report_repo=self.growth_report_repo,
            jd_analysis_repo=FakeProjectRepo(),
            resume_profile_repo=FakeProjectRepo(),
            gap_analysis_repo=FakeProjectRepo(),
            project_candidate_profile_repo=FakeProjectRepo(),
            resume_authenticity_repo=FakeProjectRepo(),
            evidence_builder=FakeEvidenceBuilder(),
            growth_report_agent=self.growth_report_agent,
        )
        self.workflow = CandidateGrowthReportWorkflow(self.nodes, runtime=self.runtime)

    async def test_workflow_generates_growth_report_and_persists_state(self):
        result = await self.workflow.run(self.session)

        self.assertEqual(result.report.id, 700)
        self.assertEqual(result.state["workflow_run_id"], "growth-run-1")
        self.assertEqual(result.state["thread_id"], "growth:session-uid")
        self.assertEqual(result.state["branch"], "generate_new_growth_report")
        self.assertEqual(result.state["growth_agent_run_id"], 888)
        self.assertEqual(result.state["growth_report_id"], 700)
        self.assertEqual(result.state["growth_report_uid"], result.report.report_uid)
        self.assertEqual(result.state["evidence_packet_id"], "growth-packet-1")
        self.assertEqual(result.state["status"], "success")
        self.assertIn("generate_growth_report", result.state["completed_steps"])
        self.assertIn("persist_growth_report", result.state["completed_steps"])
        self.assertEqual(len(self.growth_report_agent.calls), 1)
        self.assertEqual(
            result.state["outputs"]["artifacts"],
            [
                {
                    "name": "candidate_growth_report",
                    "artifact_kind": "candidate_growth_report",
                    "artifact_id": 700,
                    "source": "generated_by_workflow",
                    "required": True,
                    "status": "available",
                    "reason": None,
                }
            ],
        )
        self.assertEqual(self.runtime.saved[-1][1]["current_step"], "complete")
        self.assertEqual(self.runtime.saved[-1][1]["status"], "success")

    async def test_workflow_reuses_existing_growth_report(self):
        existing = report(777, agent_run_id=333)
        self.growth_report_repo.existing = existing

        result = await self.workflow.run(self.session)

        self.assertIs(result.report, existing)
        self.assertEqual(self.growth_report_repo.created, [])
        self.assertEqual(self.growth_report_agent.calls, [])
        self.assertEqual(result.state["branch"], "reuse_existing_growth_report")
        self.assertEqual(result.state["growth_report_id"], 777)
        self.assertEqual(result.state["growth_agent_run_id"], 333)
        self.assertIn("ensure_growth_report_reused", result.state["completed_steps"])
        self.assertEqual(self.runtime.saved[-1][1]["status"], "success")

    async def test_workflow_marks_partial_when_required_inputs_are_missing(self):
        self.nodes.message_repo = NoAnswerMessageRepo()
        self.nodes.evaluation_repo = FakeEvaluationRepo(existing=None)

        result = await self.workflow.run(self.session)

        self.assertIsNone(result.report)
        self.assertEqual(self.growth_report_repo.created, [])
        self.assertEqual(self.growth_report_agent.calls, [])
        self.assertEqual(result.state["status"], "partial")
        self.assertEqual(result.state["partial_reason"], "missing_required_growth_report_inputs")
        self.assertEqual(result.state["missing_inputs"], ["interview_answer", "evaluation"])
        self.assertEqual(result.state["branch"], "skip_growth_report_missing_inputs")
        self.assertIn("generate_growth_report", result.state["skipped_steps"])
        self.assertIn("persist_growth_report", result.state["skipped_steps"])
        self.assertEqual(self.runtime.saved[-1][1]["status"], "partial")

    async def test_workflow_marks_failure(self):
        self.nodes.growth_report_agent = FailingGrowthReportAgent()

        with self.assertRaisesRegex(RuntimeError, "growth unavailable"):
            await self.workflow.run(self.session)

        failed_save = self.runtime.saved[-1][1]
        self.assertEqual(failed_save["current_step"], "generate_growth_report")
        self.assertEqual(failed_save["status"], "failed")
        self.assertEqual(failed_save["state"]["status"], "failed")
        self.assertEqual(failed_save["last_error"]["step_id"], "generate_growth_report")
        self.assertIn("generate_growth_report", failed_save["state"]["failed_steps"])

    async def test_output_validation_failure_marks_workflow_failed_without_report(self):
        self.nodes.growth_report_agent = InvalidOutputGrowthReportAgent()

        with self.assertRaisesRegex(AgentOutputValidationError, "output.overall_summary"):
            await self.workflow.run(self.session)

        self.assertEqual(self.growth_report_repo.created, [])
        failed_save = self.runtime.saved[-1][1]
        self.assertEqual(failed_save["current_step"], "generate_growth_report")
        self.assertEqual(failed_save["status"], "failed")
        self.assertEqual(failed_save["state"]["status"], "failed")
        self.assertIn("output.overall_summary", failed_save["last_error"]["message"])
        self.assertIn("generate_growth_report", failed_save["state"]["failed_steps"])

    async def test_failed_retry_reuses_existing_growth_report(self):
        existing = report(888, agent_run_id=444)
        self.growth_report_repo.existing = existing
        self.runtime.run_obj = SimpleNamespace(
            workflow_run_id="growth-run-1",
            workflow_id="candidate_growth_report",
            thread_id="growth:session-uid",
            project_id=1,
            session_id=10,
            status="failed",
            current_step="generate_growth_report",
            state={
                "workflow_id": "candidate_growth_report",
                "workflow_run_id": "growth-run-1",
                "thread_id": "growth:session-uid",
                "status": "failed",
                "incoming_trigger": "manual_generate",
                "completed_steps": ["load_growth_context", "build_growth_evidence"],
                "failed_steps": ["generate_growth_report"],
                "last_error": {
                    "step_id": "generate_growth_report",
                    "message": "growth unavailable",
                },
            },
        )

        result = await self.workflow.run(self.session, incoming_trigger="manual_retry")

        start_state = self.runtime.saved[0][1]["state"]
        self.assertEqual(start_state["incoming_trigger"], "manual_generate")
        self.assertEqual(start_state["resume_reason"], "failed_retry")
        self.assertEqual(start_state["resume_from_step"], "generate_growth_report")
        self.assertEqual(start_state["failed_steps"], [])
        self.assertIsNone(start_state["last_error"])
        self.assertIs(result.report, existing)
        self.assertEqual(self.growth_report_agent.calls, [])
        self.assertEqual(result.state["branch"], "reuse_existing_growth_report")
        self.assertEqual(self.runtime.saved[-1][1]["status"], "success")


if __name__ == "__main__":
    unittest.main()
