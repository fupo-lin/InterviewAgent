from app.schemas.interview import GrowthReportResponse


def growth_report_response(
    *,
    session,
    report,
    status: str,
    workflow_run_id: str | None = None,
    workflow_state: dict | None = None,
) -> GrowthReportResponse:
    state = workflow_state or {}
    return GrowthReportResponse(
        sessionId=session.session_uid,
        status=status,
        workflowRunId=workflow_run_id or getattr(report, "workflow_run_id", None),
        reportId=report.id,
        reportUid=report.report_uid,
        report=report.content,
        errorMessage=None,
        missingInputs=state.get("missing_inputs") or [],
        branch=state.get("branch"),
        branchReason=state.get("branch_reason"),
        nextActions=state.get("next_actions") or [],
    )
