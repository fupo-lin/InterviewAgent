import unittest
from datetime import datetime
import sys
from types import ModuleType
from types import SimpleNamespace
from unittest.mock import patch

from service.support import configure_backend_imports

configure_backend_imports()

from fastapi import HTTPException


repository_module = ModuleType("app.repository.agent_run_repository")


class PlaceholderAgentRunRepository:
    pass


repository_module.AgentRunRepository = PlaceholderAgentRunRepository
sys.modules["app.repository.agent_run_repository"] = repository_module

from app.service.agent_run_query_service import AgentRunQueryService


def run(
    run_id: int,
    status: str = "success",
    input_snapshot: dict | None = None,
    error_message: str | None = None,
):
    return SimpleNamespace(
        id=run_id,
        agent_name="ResumeRewriteAgent",
        agent_version="1.0.0",
        task_name="resume_rewrite",
        project_id=1,
        session_id=None,
        input_schema_version="ResumeRewriteInput.v1",
        output_schema_version="ResumeRewriteResult.v1",
        prompt_id="resume_rewrite",
        prompt_version="3.0.0",
        model_name="test-model",
        input_snapshot=input_snapshot or {},
        context_refs={"resume_id": 7},
        evidence_refs=["resume_claim_1"],
        output_snapshot={"result": "ok"},
        raw_response={"raw": True},
        status=status,
        error_message=error_message,
        create_time=datetime(2026, 7, 1, 12, 0, 0),
    )


class FakeAgentRunRepository:
    def __init__(self, db):
        self.db = db
        self.runs = []
        self.list_calls = []
        self.failed_calls = []
        self.by_id = {}

    def get_by_id(self, agent_run_id: int):
        return self.by_id.get(agent_run_id)

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        return self.runs

    def list_failed(self, **kwargs):
        self.failed_calls.append(kwargs)
        return [item for item in self.runs if item.status == "failed"]


class AgentRunQueryServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        patcher = patch("app.service.agent_run_query_service.AgentRunRepository", FakeAgentRunRepository)
        self.addCleanup(patcher.stop)
        patcher.start()
        self.service = AgentRunQueryService(db=object())
        self.repo = self.service.repo

    def test_list_runs_returns_validation_summary(self):
        self.repo.runs = [
            run(
                1,
                input_snapshot={
                    "prompt_contract_validation": {
                        "ok": True,
                        "missing_context": [],
                        "missing_evidence": [],
                    },
                    "evidence_packet_validation": {
                        "ok": True,
                        "errors": [],
                        "warnings": ["Evidence item #1 content_excerpt is empty"],
                    },
                },
            )
        ]

        response = self.service.list_runs(
            project_id=1,
            session_id=None,
            status="success",
            agent_name="ResumeRewriteAgent",
            prompt_id="resume_rewrite",
            limit=500,
        )

        self.assertEqual(response.total, 1)
        self.assertEqual(self.repo.list_calls[0]["limit"], 200)
        item = response.items[0]
        self.assertEqual(item.id, 1)
        self.assertEqual(item.agent_name, "ResumeRewriteAgent")
        self.assertTrue(item.validation.prompt_contract_ok)
        self.assertTrue(item.validation.evidence_packet_ok)
        self.assertEqual(item.validation.evidence_warnings, ["Evidence item #1 content_excerpt is empty"])

    def test_list_runs_only_issues_filters_successful_clean_runs(self):
        self.repo.runs = [
            run(
                1,
                input_snapshot={
                    "prompt_contract_validation": {"ok": True},
                    "evidence_packet_validation": {"ok": True},
                },
            ),
            run(
                2,
                input_snapshot={
                    "prompt_contract_validation": {
                        "ok": False,
                        "missing_evidence": ["authenticity_check"],
                    },
                    "evidence_packet_validation": {"ok": True},
                },
            ),
            run(
                3,
                status="failed",
                error_message="model unavailable",
                input_snapshot={
                    "prompt_contract_validation": {"ok": True},
                    "evidence_packet_validation": {"ok": True},
                },
            ),
        ]

        response = self.service.list_runs(only_issues=True)

        self.assertEqual([item.id for item in response.items], [2, 3])
        self.assertEqual(response.total, 2)
        self.assertEqual(response.items[0].validation.prompt_missing_evidence, ["authenticity_check"])

    def test_failed_runs_delegates_to_repository(self):
        self.repo.runs = [
            run(1),
            run(2, status="failed", error_message="parse failed"),
        ]

        response = self.service.failed_runs(project_id=1, session_id=10, limit=0)

        self.assertEqual(self.repo.failed_calls[0], {"project_id": 1, "session_id": 10, "limit": 1})
        self.assertEqual(response.total, 1)
        self.assertEqual(response.items[0].id, 2)
        self.assertEqual(response.items[0].error_message, "parse failed")

    def test_get_detail_returns_snapshots(self):
        item = run(
            4,
            input_snapshot={
                "prompt_contract_validation": {"ok": True},
                "evidence_packet_validation": {"ok": True},
            },
        )
        self.repo.by_id[4] = item

        response = self.service.get_detail(4)

        self.assertEqual(response.id, 4)
        self.assertEqual(response.agent_version, "1.0.0")
        self.assertEqual(response.input_schema_version, "ResumeRewriteInput.v1")
        self.assertEqual(response.output_schema_version, "ResumeRewriteResult.v1")
        self.assertEqual(response.input_snapshot, item.input_snapshot)
        self.assertEqual(response.context_refs, {"resume_id": 7})
        self.assertEqual(response.output_snapshot, {"result": "ok"})
        self.assertEqual(response.raw_response, {"raw": True})

    def test_get_detail_raises_404_when_missing(self):
        with self.assertRaises(HTTPException) as exc:
            self.service.get_detail(999)

        self.assertEqual(exc.exception.status_code, 404)
        self.assertEqual(exc.exception.detail, "Agent run not found")


if __name__ == "__main__":
    unittest.main()
