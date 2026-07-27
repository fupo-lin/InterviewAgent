import sys
import unittest
from datetime import datetime
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from service.support import configure_backend_imports

configure_backend_imports()

from fastapi import HTTPException
from pydantic import ValidationError


repository_module = ModuleType("app.repository.agent_run_repository")
workflow_repository_module = ModuleType("app.repository.workflow_run_repository")


class PlaceholderAgentRunRepository:
    pass


repository_module.AgentRunRepository = PlaceholderAgentRunRepository
sys.modules["app.repository.agent_run_repository"] = repository_module


class PlaceholderWorkflowRunRepository:
    pass


workflow_repository_module.WorkflowRunRepository = PlaceholderWorkflowRunRepository
sys.modules["app.repository.workflow_run_repository"] = workflow_repository_module

from app.service.workflow_run_query_service import WorkflowRunQueryService
from app.schemas.workflow_run import WorkflowRunListQuery


def agent_run(
    run_id: int,
    workflow_id: str = "resume_optimization",
    workflow_run_id: str = "project_1_resume_optimization",
    step_id: str = "resume_rewrite",
    status: str = "success",
    project_id: int | None = 1,
    session_id: int | None = None,
):
    return SimpleNamespace(
        id=run_id,
        agent_name="ResumeRewriteAgent",
        agent_version="1.0.0",
        task_name="resume_rewrite",
        project_id=project_id,
        session_id=session_id,
        input_schema_version="ResumeRewriteInput.v1",
        output_schema_version="ResumeRewriteResult.v1",
        prompt_id="resume_rewrite",
        prompt_version="3.0.0",
        model_name="test-model",
        input_snapshot={
            "workflow_context": {
                "workflow_id": workflow_id,
                "workflow_run_id": workflow_run_id,
                "step_id": step_id,
            },
            "agent_definition_validation": {"ok": True},
            "prompt_contract_validation": {"ok": True},
            "evidence_packet_validation": {"ok": True},
        },
        context_refs={},
        evidence_refs=[],
        output_snapshot={"result": "ok"},
        raw_response={"raw": True},
        status=status,
        error_message=None if status == "success" else "failed",
        create_time=datetime(2026, 7, 2, 12, run_id, 0),
    )


class FakeAgentRunRepository:
    def __init__(self, db):
        self.db = db
        self.runs = []
        self.list_calls = []

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        items = self.runs
        if kwargs.get("project_id") is not None:
            items = [item for item in items if item.project_id == kwargs["project_id"]]
        if kwargs.get("session_id") is not None:
            items = [item for item in items if item.session_id == kwargs["session_id"]]
        return items[: kwargs.get("limit", 50)]


class FakeWorkflowRunRepository:
    def __init__(self, db):
        self.db = db
        self.runs = []
        self.list_calls = []

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        items = self.runs
        if kwargs.get("workflow_id"):
            items = [item for item in items if item.workflow_id == kwargs["workflow_id"]]
        if kwargs.get("project_id") is not None:
            items = [item for item in items if item.project_id == kwargs["project_id"]]
        if kwargs.get("session_id") is not None:
            items = [item for item in items if item.session_id == kwargs["session_id"]]
        if kwargs.get("status"):
            items = [item for item in items if item.status == kwargs["status"]]
        return items[: kwargs.get("limit", 50)]

    def get_by_workflow_run_id(self, workflow_run_id):
        for item in self.runs:
            if item.workflow_run_id == workflow_run_id:
                return item
        return None


def workflow_run(
    workflow_run_id: str = "session_10_interview_runtime",
    workflow_id: str = "interview_runtime",
    thread_id: str = "interview:session-uid",
    status: str = "waiting_user",
    current_step: str = "wait_user_answer",
    project_id: int | None = 1,
    session_id: int | None = 10,
    state: dict | None = None,
    last_error: dict | None = None,
    error_message: str | None = None,
):
    state = state or {
        "completed_steps": ["save_user_answer", "topic_judge", "generate_followup"],
        "failed_steps": [],
        "last_user_message_id": 100,
    }
    return SimpleNamespace(
        id=1,
        workflow_run_id=workflow_run_id,
        workflow_id=workflow_id,
        thread_id=thread_id,
        project_id=project_id,
        session_id=session_id,
        status=status,
        current_step=current_step,
        state=state,
        last_error=last_error,
        error_message=error_message,
        create_time=datetime(2026, 7, 2, 12, 0, 0),
        update_time=datetime(2026, 7, 2, 12, 1, 0),
    )


class WorkflowRunQueryServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        patcher = patch(
            "app.service.workflow_run_query_service.AgentRunRepository",
            FakeAgentRunRepository,
        )
        agent_run_patcher = patch(
            "app.service.agent_run_query_service.AgentRunRepository",
            FakeAgentRunRepository,
        )
        workflow_run_patcher = patch(
            "app.service.workflow_run_query_service.WorkflowRunRepository",
            FakeWorkflowRunRepository,
        )
        self.addCleanup(patcher.stop)
        self.addCleanup(agent_run_patcher.stop)
        self.addCleanup(workflow_run_patcher.stop)
        patcher.start()
        agent_run_patcher.start()
        workflow_run_patcher.start()
        self.service = WorkflowRunQueryService(db=object())
        self.repo = self.service.repo
        self.workflow_repo = self.service.workflow_repo
        self.service.agent_runs.repo = self.repo

    def test_list_runs_aggregates_workflow_context(self):
        self.repo.runs = [
            agent_run(1, step_id="resume_authenticity"),
            agent_run(2, step_id="resume_rewrite"),
            agent_run(
                3,
                workflow_id="preparation",
                workflow_run_id="project_1_preparation",
                step_id="interview_plan",
            ),
        ]

        response = self.service.list_runs(workflow_id="resume_optimization", project_id=1)

        self.assertEqual(response.total, 1)
        item = response.items[0]
        self.assertEqual(item.workflow_run_id, "project_1_resume_optimization")
        self.assertEqual(item.workflow_id, "resume_optimization")
        self.assertEqual(item.status, "success")
        self.assertEqual(item.completed_steps, ["resume_authenticity", "resume_rewrite"])
        self.assertEqual(item.failed_steps, [])
        self.assertEqual(item.missing_required_steps, [])
        self.assertEqual(item.agent_run_count, 2)
        self.assertEqual(item.latest_agent_run_id, 2)
        self.assertEqual(self.repo.list_calls[0]["project_id"], 1)
        self.assertEqual(self.repo.list_calls[0]["limit"], 1000)

    def test_list_runs_accepts_fixed_query_schema(self):
        self.repo.runs = [
            agent_run(1, step_id="resume_authenticity"),
            agent_run(2, step_id="resume_rewrite"),
        ]
        query = WorkflowRunListQuery(
            workflowId="resume_optimization",
            projectId=1,
            status="success",
            limit=20,
        )

        response = self.service.list_runs(query)

        self.assertEqual(response.total, 1)
        self.assertEqual(response.items[0].workflow_run_id, "project_1_resume_optimization")
        self.assertEqual(self.workflow_repo.list_calls[0]["workflow_id"], "resume_optimization")
        self.assertEqual(self.workflow_repo.list_calls[0]["project_id"], 1)
        self.assertEqual(self.workflow_repo.list_calls[0]["status"], "success")
        self.assertEqual(self.workflow_repo.list_calls[0]["limit"], 20)

    def test_query_schema_rejects_unstable_status_values(self):
        with self.assertRaises(ValidationError):
            WorkflowRunListQuery(status="paused")

    def test_list_response_schema_uses_fixed_aliases(self):
        self.workflow_repo.runs = [workflow_run()]

        response = self.service.list_runs(workflow_id="interview_runtime", session_id=10)
        payload = response.model_dump(by_alias=True)

        self.assertEqual(payload["total"], 1)
        item = payload["items"][0]
        self.assertIn("workflowRunId", item)
        self.assertIn("workflowId", item)
        self.assertIn("threadId", item)
        self.assertIn("currentStep", item)
        self.assertIn("activeStep", item)
        self.assertIn("resumeReason", item)
        self.assertIn("resumeFromStep", item)
        self.assertIn("completedSteps", item)
        self.assertIn("failedSteps", item)
        self.assertIn("missingRequiredSteps", item)
        self.assertIn("errorMessage", item)
        self.assertIn("agentRunCount", item)
        self.assertIn("latestAgentRunId", item)
        self.assertIn("createTime", item)
        self.assertIn("updateTime", item)
        self.assertNotIn("workflow_run_id", item)
        self.assertNotIn("current_step", item)

    def test_detail_response_schema_uses_fixed_aliases(self):
        self.workflow_repo.runs = [
            workflow_run(
                state={
                    "completed_steps": ["save_user_answer"],
                    "failed_steps": [],
                    "last_user_message_id": 100,
                    "step_metrics": [
                        {
                            "step_id": "save_user_answer",
                            "status": "success",
                            "latency_ms": 12,
                            "current_step": "save_user_answer",
                            "recorded_at": "2026-07-17T00:00:00+00:00",
                        }
                    ],
                },
                last_error={
                    "step_id": "generate_followup",
                    "message": "followup unavailable",
                },
            )
        ]
        self.repo.runs = [
            agent_run(
                1,
                workflow_id="interview_runtime",
                workflow_run_id="session_10_interview_runtime",
                step_id="topic_completion_judge",
                session_id=10,
            )
        ]

        response = self.service.get_detail("session_10_interview_runtime")
        payload = response.model_dump(by_alias=True)

        self.assertIn("workflowRunId", payload)
        self.assertIn("currentStep", payload)
        self.assertIn("agentRuns", payload)
        self.assertIn("lastError", payload)
        self.assertIn("state", payload)
        self.assertIn("steps", payload)
        self.assertIn("stepMetricsSummary", payload)
        self.assertIn("stepMetrics", payload)
        self.assertIn("stepId", payload["steps"][0])
        self.assertIn("agentRunIds", payload["steps"][0])
        self.assertIn("latestAgentRunId", payload["steps"][0])
        self.assertIn("runCount", payload["steps"][0])
        self.assertIn("stepCount", payload["stepMetricsSummary"])
        self.assertIn("failedStepCount", payload["stepMetricsSummary"])
        self.assertIn("totalLatencyMs", payload["stepMetricsSummary"])
        self.assertIn("lastStepId", payload["stepMetricsSummary"])
        self.assertIn("stepId", payload["stepMetrics"][0])
        self.assertIn("latencyMs", payload["stepMetrics"][0])
        self.assertIn("currentStep", payload["stepMetrics"][0])
        self.assertIn("recordedAt", payload["stepMetrics"][0])
        self.assertIn("agentName", payload["agentRuns"][0])
        self.assertIn("workflowRunId", payload["agentRuns"][0]["workflow"])
        self.assertNotIn("workflow_run_id", payload)
        self.assertNotIn("agent_runs", payload)
        self.assertNotIn("last_error", payload)
        self.assertNotIn("step_metrics_summary", payload)
        self.assertNotIn("step_metrics", payload)

    def test_list_runs_prefers_persisted_workflow_runs(self):
        self.workflow_repo.runs = [workflow_run()]
        self.repo.runs = [
            agent_run(
                1,
                workflow_id="interview_runtime",
                workflow_run_id="session_10_interview_runtime",
                step_id="topic_completion_judge",
                session_id=10,
            )
        ]

        response = self.service.list_runs(workflow_id="interview_runtime", session_id=10)

        self.assertEqual(response.total, 1)
        item = response.items[0]
        self.assertEqual(item.workflow_run_id, "session_10_interview_runtime")
        self.assertEqual(item.thread_id, "interview:session-uid")
        self.assertEqual(item.status, "waiting_user")
        self.assertEqual(item.current_step, "wait_user_answer")
        self.assertIsNone(item.active_step)
        self.assertIsNone(item.resume_reason)
        self.assertIsNone(item.resume_from_step)
        self.assertIsNone(item.error_message)
        self.assertEqual(item.completed_steps, ["save_user_answer", "topic_judge", "generate_followup"])
        self.assertEqual(item.agent_run_count, 1)
        self.assertEqual(item.latest_agent_run_id, 1)
        self.assertEqual(self.workflow_repo.list_calls[0]["session_id"], 10)

    def test_list_runs_marks_missing_required_step_as_partial(self):
        self.repo.runs = [
            agent_run(1, step_id="resume_authenticity"),
        ]

        response = self.service.list_runs(workflow_id="resume_optimization")

        self.assertEqual(response.total, 1)
        item = response.items[0]
        self.assertEqual(item.status, "partial")
        self.assertEqual(item.missing_required_steps, ["resume_rewrite"])

    def test_list_runs_marks_failed_step(self):
        self.repo.runs = [
            agent_run(1, step_id="resume_authenticity"),
            agent_run(2, step_id="resume_rewrite", status="failed"),
        ]

        response = self.service.list_runs(status="failed")

        self.assertEqual(response.total, 1)
        item = response.items[0]
        self.assertEqual(item.status, "failed")
        self.assertEqual(item.failed_steps, ["resume_rewrite"])

    def test_get_detail_returns_steps_and_agent_runs(self):
        self.repo.runs = [
            agent_run(1, step_id="resume_authenticity"),
            agent_run(2, step_id="resume_rewrite"),
        ]

        response = self.service.get_detail("project_1_resume_optimization")

        self.assertEqual(response.workflow_run_id, "project_1_resume_optimization")
        self.assertEqual(response.status, "success")
        self.assertEqual([step.step_id for step in response.steps], ["resume_authenticity", "resume_rewrite"])
        self.assertEqual(response.steps[0].agent_run_ids, [1])
        self.assertEqual(response.steps[1].latest_agent_run_id, 2)
        self.assertEqual([item.id for item in response.agent_runs], [1, 2])

    def test_get_detail_prefers_persisted_workflow_run_state(self):
        self.workflow_repo.runs = [workflow_run()]
        self.repo.runs = [
            agent_run(
                1,
                workflow_id="interview_runtime",
                workflow_run_id="session_10_interview_runtime",
                step_id="topic_completion_judge",
                session_id=10,
            )
        ]

        response = self.service.get_detail("session_10_interview_runtime")

        self.assertEqual(response.workflow_run_id, "session_10_interview_runtime")
        self.assertEqual(response.thread_id, "interview:session-uid")
        self.assertEqual(response.status, "waiting_user")
        self.assertEqual(response.current_step, "wait_user_answer")
        self.assertIsNone(response.active_step)
        self.assertIsNone(response.resume_reason)
        self.assertIsNone(response.resume_from_step)
        self.assertIsNone(response.error_message)
        self.assertEqual(response.state["last_user_message_id"], 100)
        self.assertEqual(response.last_error, None)
        self.assertEqual([item.id for item in response.agent_runs], [1])
        self.assertIn("topic_completion_judge", [step.step_id for step in response.steps])

    def test_get_detail_exposes_step_metrics_from_persisted_state(self):
        self.workflow_repo.runs = [
            workflow_run(
                state={
                    "completed_steps": ["save_user_answer"],
                    "failed_steps": ["generate_followup"],
                    "step_metrics": [
                        {
                            "step_id": "save_user_answer",
                            "status": "success",
                            "latency_ms": 12,
                            "current_step": "save_user_answer",
                            "recorded_at": "2026-07-17T00:00:00+00:00",
                        },
                        {
                            "step_id": "generate_followup",
                            "status": "failed",
                            "latency_ms": 34,
                            "current_step": "generate_followup",
                            "recorded_at": "2026-07-17T00:00:01+00:00",
                            "error_type": "RuntimeError",
                            "error_message": "boom",
                        },
                    ],
                },
            )
        ]

        response = self.service.get_detail("session_10_interview_runtime")

        self.assertEqual(response.step_metrics_summary.step_count, 2)
        self.assertEqual(response.step_metrics_summary.failed_step_count, 1)
        self.assertEqual(response.step_metrics_summary.total_latency_ms, 46)
        self.assertEqual(response.step_metrics_summary.last_step_id, "generate_followup")
        self.assertEqual(
            [item.step_id for item in response.step_metrics],
            ["save_user_answer", "generate_followup"],
        )
        self.assertEqual(response.step_metrics[0].latency_ms, 12)
        self.assertEqual(response.step_metrics[1].status, "failed")
        self.assertEqual(response.step_metrics[1].error_type, "RuntimeError")
        self.assertEqual(response.step_metrics[1].error_message, "boom")

    def test_persisted_workflow_run_exposes_resume_observability_fields(self):
        self.workflow_repo.runs = [
            workflow_run(
                status="failed",
                current_step="generate_followup",
                state={
                    "active_step": "generate_followup",
                    "resume_reason": "failed_retry",
                    "resume_from_step": "generate_followup",
                    "completed_steps": ["save_user_answer", "advance_execution"],
                    "failed_steps": ["generate_followup"],
                    "last_user_message_id": 100,
                },
                last_error={
                    "step_id": "generate_followup",
                    "message": "followup unavailable",
                },
                error_message="followup unavailable",
            )
        ]

        response = self.service.get_detail("session_10_interview_runtime")

        self.assertEqual(response.status, "failed")
        self.assertEqual(response.current_step, "generate_followup")
        self.assertEqual(response.active_step, "generate_followup")
        self.assertEqual(response.resume_reason, "failed_retry")
        self.assertEqual(response.resume_from_step, "generate_followup")
        self.assertEqual(response.error_message, "followup unavailable")
        self.assertEqual(response.failed_steps, ["generate_followup"])
        self.assertEqual(response.last_error["step_id"], "generate_followup")

    def test_list_runs_can_filter_post_interview_assessment_workflow(self):
        self.workflow_repo.runs = [
            workflow_run(
                workflow_run_id="assessment_1",
                workflow_id="post_interview_assessment",
                thread_id="assessment:session-uid",
                status="success",
                current_step="complete",
                state={
                    "active_step": None,
                    "resume_reason": "new_trigger",
                    "resume_from_step": None,
                    "completed_steps": [
                        "load_assessment_context",
                        "evaluation",
                        "ensure_evaluation",
                        "complete",
                    ],
                    "failed_steps": [],
                    "evaluation_id": 900,
                    "branch": "generated_evaluation",
                    "output_contract_version": "PostInterviewAssessmentOutput.v1",
                    "outputs": {
                        "contract_version": "PostInterviewAssessmentOutput.v1",
                        "artifacts": [
                            {
                                "name": "evaluation",
                                "artifact_kind": "interview_evaluation",
                                "artifact_id": 900,
                                "source": "generated_by_workflow",
                                "required": True,
                                "status": "available",
                                "reason": None,
                            }
                        ],
                        "next_actions": [],
                    },
                },
            ),
            workflow_run(
                workflow_run_id="runtime_1",
                workflow_id="interview_runtime",
                thread_id="interview:session-uid",
            ),
        ]

        response = self.service.list_runs(workflow_id="post_interview_assessment")

        self.assertEqual(response.total, 1)
        item = response.items[0]
        self.assertEqual(item.workflow_run_id, "assessment_1")
        self.assertEqual(item.workflow_id, "post_interview_assessment")
        self.assertEqual(item.thread_id, "assessment:session-uid")
        self.assertEqual(item.status, "success")
        self.assertEqual(item.current_step, "complete")
        self.assertEqual(item.resume_reason, "new_trigger")
        self.assertEqual(
            item.completed_steps,
            ["load_assessment_context", "evaluation", "ensure_evaluation", "complete"],
        )
        self.assertEqual(self.workflow_repo.list_calls[0]["workflow_id"], "post_interview_assessment")

        detail = self.service.get_detail("assessment_1")

        self.assertEqual(
            detail.state["outputs"]["artifacts"][0],
            {
                "name": "evaluation",
                "artifact_kind": "interview_evaluation",
                "artifact_id": 900,
                "source": "generated_by_workflow",
                "required": True,
                "status": "available",
                "reason": None,
            },
        )

    def test_detail_marks_skipped_assessment_steps(self):
        self.workflow_repo.runs = [
            workflow_run(
                workflow_run_id="assessment_partial",
                workflow_id="post_interview_assessment",
                thread_id="assessment:session-uid",
                status="partial",
                current_step="complete",
                state={
                    "active_step": None,
                    "resume_reason": "new_trigger",
                    "completed_steps": [
                        "load_assessment_context",
                        "complete",
                    ],
                    "skipped_steps": [
                        "evaluation",
                        "ensure_evaluation",
                    ],
                    "failed_steps": [],
                    "partial_reason": "insufficient_transcript",
                    "branch": "skip_evaluation_insufficient_transcript",
                    "outputs": {
                        "contract_version": "PostInterviewAssessmentOutput.v1",
                        "artifacts": [
                            {
                                "name": "evaluation",
                                "artifact_kind": "interview_evaluation",
                                "artifact_id": None,
                                "source": "skipped_by_workflow",
                                "required": True,
                                "status": "skipped",
                                "reason": "insufficient_transcript",
                            }
                        ],
                        "next_actions": [],
                    },
                },
            ),
        ]

        response = self.service.get_detail("assessment_partial")

        self.assertEqual(response.status, "partial")
        evaluation_step = next(item for item in response.steps if item.step_id == "evaluation")
        self.assertEqual(evaluation_step.status, "skipped")
        self.assertEqual(response.state["partial_reason"], "insufficient_transcript")
        self.assertEqual(response.state["outputs"]["artifacts"][0]["status"], "skipped")

    def test_get_detail_links_persisted_runtime_run_with_real_workflow_run_id(self):
        runtime_workflow_run_id = "interview_runtime_abc123"
        self.workflow_repo.runs = [
            workflow_run(
                workflow_run_id=runtime_workflow_run_id,
                workflow_id="interview_runtime",
            )
        ]
        self.repo.runs = [
            agent_run(
                1,
                workflow_id="interview_runtime",
                workflow_run_id=runtime_workflow_run_id,
                step_id="topic_completion_judge",
                session_id=10,
            ),
            agent_run(
                2,
                workflow_id="interview_runtime",
                workflow_run_id=runtime_workflow_run_id,
                step_id="followup",
                session_id=10,
            ),
            agent_run(
                3,
                workflow_id="interview_runtime",
                workflow_run_id="session_10_interview_runtime",
                step_id="followup",
                session_id=10,
            ),
        ]

        response = self.service.get_detail(runtime_workflow_run_id)

        self.assertEqual(response.workflow_run_id, runtime_workflow_run_id)
        self.assertEqual(response.agent_run_count, 2)
        self.assertEqual(response.latest_agent_run_id, 2)
        self.assertEqual([item.id for item in response.agent_runs], [1, 2])
        steps = {step.step_id: step for step in response.steps}
        self.assertEqual(steps["topic_completion_judge"].agent_run_ids, [1])
        self.assertEqual(steps["followup"].agent_run_ids, [2])
        self.assertEqual(steps["followup"].latest_agent_run_id, 2)

    def test_get_detail_raises_404_when_missing(self):
        with self.assertRaises(HTTPException) as exc:
            self.service.get_detail("missing_run")

        self.assertEqual(exc.exception.status_code, 404)
        self.assertEqual(exc.exception.detail, "Workflow run not found")


if __name__ == "__main__":
    unittest.main()
