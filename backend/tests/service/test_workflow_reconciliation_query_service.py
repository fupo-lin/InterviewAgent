import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from service.support import configure_backend_imports

configure_backend_imports()

from fastapi import HTTPException


agent_repository_module = ModuleType("app.repository.agent_run_repository")
interview_repository_module = ModuleType("app.repository.interview_repository")
workflow_repository_module = ModuleType("app.repository.workflow_run_repository")


class PlaceholderAgentRunRepository:
    pass


class PlaceholderInterviewMessageRepository:
    pass


class PlaceholderInterviewPlanExecutionRepository:
    pass


class PlaceholderWorkflowRunRepository:
    pass


agent_repository_module.AgentRunRepository = PlaceholderAgentRunRepository
interview_repository_module.InterviewMessageRepository = PlaceholderInterviewMessageRepository
interview_repository_module.InterviewPlanExecutionRepository = PlaceholderInterviewPlanExecutionRepository
workflow_repository_module.WorkflowRunRepository = PlaceholderWorkflowRunRepository
sys.modules["app.repository.agent_run_repository"] = agent_repository_module
sys.modules["app.repository.interview_repository"] = interview_repository_module
sys.modules["app.repository.workflow_run_repository"] = workflow_repository_module

from app.service.workflow_reconciliation_query_service import WorkflowReconciliationQueryService


def workflow_run():
    return SimpleNamespace(
        workflow_run_id="interview_runtime_abc",
        thread_id="interview:session-uid",
        session_id=10,
        status="waiting_user",
        current_step="wait_user_answer",
        state={
            "thread_id": "interview:session-uid",
            "session_id": 10,
            "last_user_message_id": 100,
            "last_assistant_message_id": 101,
            "last_topic_judge_agent_run_id": 501,
            "last_followup_agent_run_id": 601,
            "completed_steps": ["save_user_answer", "advance_execution"],
            "failed_steps": [],
        },
        last_error=None,
    )


def message(message_id, role_type, message_type):
    return SimpleNamespace(
        id=message_id,
        role_type=role_type,
        message_type=message_type,
        status="normal",
    )


class FakeWorkflowRunRepository:
    runs = {}

    def __init__(self, db):
        self.db = db

    def get_by_workflow_run_id(self, workflow_run_id):
        return self.runs.get(workflow_run_id)


class FakeMessageRepository:
    def __init__(self, db):
        self.db = db

    def list_by_session_id(self, session_id):
        return [
            message(100, "user", "answer"),
            message(101, "assistant", "followup"),
        ]


class FakeAgentRunRepository:
    def __init__(self, db):
        self.db = db

    def get_by_id(self, agent_run_id):
        if agent_run_id in {501, 601}:
            return SimpleNamespace(id=agent_run_id)
        return None


class FakeExecutionRepository:
    def __init__(self, db):
        self.db = db

    def get_latest_by_session_id(self, session_id):
        return SimpleNamespace(
            state={
                "sections": [
                    {
                        "section_key": "system_design",
                        "evidence": [{"answer_message_id": 100}],
                    }
                ]
            }
        )


class WorkflowReconciliationQueryServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        FakeWorkflowRunRepository.runs = {}
        patchers = [
            patch(
                "app.service.workflow_reconciliation_query_service.WorkflowRunRepository",
                FakeWorkflowRunRepository,
            ),
            patch(
                "app.service.workflow_reconciliation_query_service.InterviewMessageRepository",
                FakeMessageRepository,
            ),
            patch(
                "app.service.workflow_reconciliation_query_service.AgentRunRepository",
                FakeAgentRunRepository,
            ),
            patch(
                "app.service.workflow_reconciliation_query_service.InterviewPlanExecutionRepository",
                FakeExecutionRepository,
            ),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.service = WorkflowReconciliationQueryService(db=object())

    def test_get_reconciliation_returns_stable_payload(self):
        FakeWorkflowRunRepository.runs["interview_runtime_abc"] = workflow_run()

        payload = self.service.get_reconciliation("interview_runtime_abc")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["errors"], [])
        self.assertEqual(payload["warnings"], [])
        self.assertEqual(payload["metadata"]["workflow_run_id"], "interview_runtime_abc")
        self.assertIn("checks", payload)
        self.assertIn("last_user_message_exists", [check["name"] for check in payload["checks"]])

    def test_get_reconciliation_raises_404_when_workflow_run_missing(self):
        with self.assertRaises(HTTPException) as exc:
            self.service.get_reconciliation("missing")

        self.assertEqual(exc.exception.status_code, 404)
        self.assertEqual(exc.exception.detail, "Workflow run not found")


if __name__ == "__main__":
    unittest.main()
