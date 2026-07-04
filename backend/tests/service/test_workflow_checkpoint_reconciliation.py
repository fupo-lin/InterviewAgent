import unittest
from types import SimpleNamespace

from service.support import configure_backend_imports

configure_backend_imports()

from app.service.workflow_checkpoint_reconciliation import (
    WorkflowCheckpointReconciliationService,
)


def workflow_run(
    *,
    status="waiting_user",
    current_step="wait_user_answer",
    state=None,
    last_error=None,
):
    return SimpleNamespace(
        workflow_run_id="interview_runtime_abc",
        workflow_id="interview_runtime",
        thread_id="interview:session-uid",
        session_id=10,
        status=status,
        current_step=current_step,
        state=state
        or {
            "thread_id": "interview:session-uid",
            "session_id": 10,
            "last_user_message_id": 100,
            "last_assistant_message_id": 101,
            "last_topic_judge_agent_run_id": 501,
            "last_followup_agent_run_id": 601,
            "completed_steps": [
                "save_user_answer",
                "topic_judge",
                "advance_execution",
                "generate_followup",
                "save_assistant_message",
            ],
            "failed_steps": [],
        },
        last_error=last_error,
    )


def message(message_id, role_type, message_type):
    return SimpleNamespace(
        id=message_id,
        role_type=role_type,
        message_type=message_type,
        status="normal",
    )


def execution_with_marker(answer_message_id=100):
    return SimpleNamespace(
        state={
            "sections": [
                {
                    "section_key": "system_design",
                    "evidence": [{"answer_message_id": answer_message_id}],
                }
            ]
        }
    )


class FakeMessageRepo:
    def __init__(self, messages=None):
        self.messages = messages or [
            message(100, "user", "answer"),
            message(101, "assistant", "followup"),
        ]

    def list_by_session_id(self, session_id):
        return self.messages


class FakeAgentRunRepo:
    def __init__(self, run_ids=None):
        self.run_ids = set(run_ids or [501, 601])

    def get_by_id(self, agent_run_id):
        if agent_run_id in self.run_ids:
            return SimpleNamespace(id=agent_run_id)
        return None


class FakeExecutionRepo:
    def __init__(self, execution=None):
        self.execution = execution if execution is not None else execution_with_marker()

    def get_latest_by_session_id(self, session_id):
        return self.execution


class WorkflowCheckpointReconciliationTest(unittest.TestCase):
    def service(
        self,
        *,
        messages=None,
        agent_run_ids=None,
        execution=None,
    ):
        return WorkflowCheckpointReconciliationService(
            message_repo=FakeMessageRepo(messages),
            agent_run_repo=FakeAgentRunRepo(agent_run_ids),
            execution_repo=FakeExecutionRepo(execution),
        )

    def test_reconcile_ok_when_state_matches_db_artifacts(self):
        result = self.service().reconcile(workflow_run())

        self.assertTrue(result.ok)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.warnings, [])
        self.assertEqual(result.metadata["thread_id"], "interview:session-uid")
        checks = {check.name: check for check in result.checks}
        self.assertTrue(checks["last_user_message_exists"].ok)
        self.assertTrue(checks["last_assistant_message_exists"].ok)
        self.assertTrue(checks["last_topic_judge_agent_run_exists"].ok)
        self.assertTrue(checks["last_followup_agent_run_exists"].ok)
        self.assertTrue(checks["advance_execution_marker_exists"].ok)

    def test_missing_user_message_is_error(self):
        result = self.service(
            messages=[message(101, "assistant", "followup")]
        ).reconcile(workflow_run())

        self.assertFalse(result.ok)
        self.assertIn(
            "last_user_message_id=100 is missing from interview_messages",
            result.errors,
        )

    def test_missing_followup_agent_run_is_error(self):
        result = self.service(agent_run_ids=[501]).reconcile(workflow_run())

        self.assertFalse(result.ok)
        self.assertIn(
            "last_followup_agent_run_id=601 is missing from agent_runs",
            result.errors,
        )

    def test_missing_execution_marker_is_warning_not_error(self):
        result = self.service(
            execution=execution_with_marker(answer_message_id=999)
        ).reconcile(workflow_run())

        self.assertTrue(result.ok)
        self.assertIn(
            "execution does not contain answer_message_id=100",
            result.warnings,
        )

    def test_failed_workflow_without_last_error_is_error(self):
        result = self.service().reconcile(
            workflow_run(
                status="failed",
                current_step="generate_followup",
                state={
                    "thread_id": "interview:session-uid",
                    "session_id": 10,
                    "last_user_message_id": 100,
                    "completed_steps": ["save_user_answer"],
                    "failed_steps": ["generate_followup"],
                },
                last_error=None,
            )
        )

        self.assertFalse(result.ok)
        self.assertIn(
            "workflow status is failed but last_error is missing",
            result.errors,
        )

    def test_to_dict_uses_stable_shape(self):
        payload = self.service().reconcile(workflow_run()).to_dict()

        self.assertIn("ok", payload)
        self.assertIn("errors", payload)
        self.assertIn("warnings", payload)
        self.assertIn("checks", payload)
        self.assertIn("metadata", payload)
        self.assertIn("name", payload["checks"][0])
        self.assertIn("detail", payload["checks"][0])


if __name__ == "__main__":
    unittest.main()
