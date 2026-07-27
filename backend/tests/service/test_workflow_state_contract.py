import unittest

from service.support import configure_backend_imports

configure_backend_imports()

from app.service.workflow_state_contract import (
    WorkflowStateContractError,
    WorkflowStateValidator,
)


class WorkflowStateContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = WorkflowStateValidator()

    def test_accepts_valid_interview_runtime_state(self):
        state = self.validator.validate(
            {
                "workflow_id": "interview_runtime",
                "workflow_run_id": "runtime-run-1",
                "thread_id": "interview:session-uid",
                "status": "waiting_user",
                "active_step": None,
                "project_id": 1,
                "session_id": 10,
                "session_uid": "session-uid",
                "role_name": "Backend Engineer",
                "interview_plan_id": 20,
                "current_section_index": 0,
                "current_section_round_no": 1,
                "total_completed_round_no": 1,
                "incoming_user_input": "answer",
                "expected_user_round_no": 3,
                "last_assistant_message_id": 101,
                "completed_steps": ["save_user_answer"],
                "failed_steps": [],
                "last_memory_agent_run_ids": [],
                "last_error": None,
            }
        )

        self.assertEqual(state["workflow_id"], "interview_runtime")
        self.assertEqual(state["status"], "waiting_user")

    def test_rejects_interview_runtime_state_type_drift(self):
        with self.assertRaises(WorkflowStateContractError) as exc:
            self.validator.validate(
                {
                    "workflow_id": "interview_runtime",
                    "thread_id": "interview:session-uid",
                    "status": "waiting_user",
                    "session_id": "10",
                    "session_uid": "session-uid",
                    "role_name": "Backend Engineer",
                    "current_section_index": 0,
                    "current_section_round_no": 1,
                    "total_completed_round_no": 1,
                    "last_assistant_message_id": 101,
                }
            )

        self.assertEqual(exc.exception.workflow_id, "interview_runtime")
        self.assertTrue(any("session_id" in item for item in exc.exception.errors))

    def test_rejects_waiting_user_without_assistant_message(self):
        with self.assertRaises(WorkflowStateContractError) as exc:
            self.validator.validate(
                {
                    "workflow_id": "interview_runtime",
                    "thread_id": "interview:session-uid",
                    "status": "waiting_user",
                    "session_id": 10,
                    "session_uid": "session-uid",
                    "role_name": "Backend Engineer",
                    "current_section_index": 0,
                    "current_section_round_no": 1,
                    "total_completed_round_no": 1,
                }
            )

        self.assertTrue(
            any("last_assistant_message_id" in item for item in exc.exception.errors)
        )

    def test_rejects_partial_growth_report_without_missing_inputs(self):
        with self.assertRaises(WorkflowStateContractError) as exc:
            self.validator.validate(
                {
                    "workflow_id": "candidate_growth_report",
                    "thread_id": "growth:session-uid",
                    "status": "partial",
                    "session_id": 10,
                    "session_uid": "session-uid",
                    "incoming_trigger": "manual_generate",
                    "completed_steps": ["load_growth_context"],
                    "failed_steps": [],
                    "skipped_steps": ["generate_growth_report"],
                    "last_error": None,
                    "partial_reason": "missing_required_growth_report_inputs",
                    "missing_inputs": [],
                    "outputs": {},
                    "next_actions": [],
                }
            )

        self.assertTrue(any("missing_inputs" in item for item in exc.exception.errors))

    def test_unknown_workflow_state_is_left_compatible(self):
        state = {"workflow_id": "custom_workflow", "thread_id": "custom:1"}

        self.assertEqual(self.validator.validate(state), state)


if __name__ == "__main__":
    unittest.main()
