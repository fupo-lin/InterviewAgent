import unittest
from types import SimpleNamespace

from service.support import configure_backend_imports

configure_backend_imports()

from app.schemas.interview import GrowthReportResponse
from app.service.growth_report_response import growth_report_response


class GrowthReportResponseTest(unittest.TestCase):
    def test_growth_report_response_includes_workflow_diagnostics(self):
        session = SimpleNamespace(session_uid="session-uid")
        report = SimpleNamespace(
            id=700,
            report_uid="report-uid",
            workflow_run_id="growth-run-1",
            content={"overall_summary": {"level": "medium"}},
        )

        response = growth_report_response(
            session=session,
            report=report,
            status="success",
            workflow_state={
                "missing_inputs": [],
                "branch": "generate_new_growth_report",
                "branch_reason": "no_existing_growth_report",
                "next_actions": [{"type": "view_report", "reason": "growth_report_available"}],
            },
        )

        payload = response.model_dump(by_alias=True)
        self.assertEqual(payload["sessionId"], "session-uid")
        self.assertEqual(payload["workflowRunId"], "growth-run-1")
        self.assertEqual(payload["branch"], "generate_new_growth_report")
        self.assertEqual(payload["branchReason"], "no_existing_growth_report")
        self.assertEqual(payload["nextActions"][0]["type"], "view_report")

    def test_growth_report_response_serializes_partial_state_aliases(self):
        response = GrowthReportResponse(
            sessionId="session-uid",
            status="partial",
            workflowRunId="growth-run-1",
            reportId=None,
            reportUid=None,
            report=None,
            errorMessage="missing_required_growth_report_inputs",
            missingInputs=["interview_answer", "evaluation"],
            branch="skip_growth_report_missing_inputs",
            branchReason="missing_required_inputs",
            nextActions=[
                {
                    "type": "collect_required_inputs",
                    "reason": "missing_required_growth_report_inputs",
                }
            ],
        )

        payload = response.model_dump(by_alias=True)
        self.assertEqual(payload["missingInputs"], ["interview_answer", "evaluation"])
        self.assertEqual(payload["branch"], "skip_growth_report_missing_inputs")
        self.assertEqual(payload["branchReason"], "missing_required_inputs")
        self.assertEqual(payload["nextActions"][0]["type"], "collect_required_inputs")


if __name__ == "__main__":
    unittest.main()
