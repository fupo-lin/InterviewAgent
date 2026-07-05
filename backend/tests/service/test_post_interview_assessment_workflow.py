import unittest
from types import SimpleNamespace

from service.support import configure_backend_imports

configure_backend_imports()

from app.service.post_interview_assessment_nodes import PostInterviewAssessmentNodes
from app.service.post_interview_assessment_workflow import PostInterviewAssessmentWorkflow


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


def evaluation(evaluation_id: int = 900, agent_run_id: int | None = 801):
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
        agent_run_id=agent_run_id,
        schema_version="InterviewEvaluation.v1",
        evidence_refs=["interview_answer_2"],
    )


class FakeMessageRepo:
    def __init__(self) -> None:
        self.messages = [
            message(1, "assistant", "Please introduce your project."),
            message(2, "user", "I built retry handling.", round_no=2),
        ]

    def latest_completed_round_no(self, session_id):
        return 2

    def list_by_session_id(self, session_id):
        return self.messages

    def list_recent_rounds(self, session_id, rounds):
        return self.messages


class NoAnswerMessageRepo(FakeMessageRepo):
    def __init__(self) -> None:
        self.messages = [
            message(1, "assistant", "Please introduce your project."),
        ]

    def latest_completed_round_no(self, session_id):
        return 0


class FakeEvaluationRepo:
    def __init__(self, existing=None) -> None:
        self.existing = existing
        self.created = []

    def get_latest_by_session_id(self, session_id):
        return self.existing

    def create(self, **kwargs):
        item = evaluation(900 + len(self.created), kwargs.get("agent_run_id"))
        for key, value in kwargs.items():
            setattr(item, key, value)
        self.created.append(item)
        self.existing = item
        return item


class FakeSummaryRepo:
    def get_latest_by_session_id(self, session_id, summary_type):
        return None


class FakeExecutionRepo:
    def __init__(self) -> None:
        self.execution = SimpleNamespace(
            id=40,
            state={"sections": [{"section_key": "system_design", "evidence": []}]},
            status="active",
        )

    def get_latest_by_session_id(self, session_id):
        return self.execution


class FakePlanRepo:
    def get_by_id(self, plan_id):
        return SimpleNamespace(
            id=plan_id,
            plan_mode="jd_resume",
            content={"role_name": "Backend Engineer", "sections": []},
        )


class FakeSessionRepo:
    def __init__(self) -> None:
        self.finished = []

    def mark_finished(self, session):
        session.status = "finished"
        self.finished.append(session.id)
        return session


class FakeExecutionService:
    def __init__(self) -> None:
        self.finished = []

    def mark_finished(self, session_id):
        self.finished.append(session_id)


class FakeWorkflowRuntime:
    def __init__(self) -> None:
        self.repository = self
        self.run_obj = None
        self.saved = []

    def load_or_create(self, **kwargs):
        if self.run_obj:
            return self.run_obj
        self.run_obj = SimpleNamespace(
            workflow_run_id="assessment-run-1",
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

    def get_by_workflow_run_id(self, workflow_run_id):
        if self.run_obj and self.run_obj.workflow_run_id == workflow_run_id:
            return self.run_obj
        return None


class FakeEvaluationAgent:
    def __init__(self) -> None:
        self.calls = []

    async def run(self, agent_input):
        self.calls.append(agent_input)
        return SimpleNamespace(
            output={
                "strengths": "clear project context",
                "weaknesses": "needs metrics",
                "suggestions": "prepare numbers",
                "summary": "ok",
                "technical_ability": "medium",
                "project_experience": "medium",
                "communication": "clear",
                "improvement_suggestions": "prepare numbers",
            },
            raw_response={"raw": "evaluation"},
            agent_run=SimpleNamespace(id=801),
            output_schema="InterviewEvaluation.v1",
            evidence_refs=["interview_answer_2"],
        )


class FailingEvaluationAgent:
    async def run(self, agent_input):
        raise RuntimeError("evaluation unavailable")


class PostInterviewAssessmentWorkflowTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.session = SimpleNamespace(
            id=10,
            session_uid="session-uid",
            project_id=1,
            role_name="Backend Engineer",
            interview_plan_id=20,
            status="active",
        )
        self.message_repo = FakeMessageRepo()
        self.evaluation_repo = FakeEvaluationRepo()
        self.summary_repo = FakeSummaryRepo()
        self.execution_repo = FakeExecutionRepo()
        self.plan_repo = FakePlanRepo()
        self.session_repo = FakeSessionRepo()
        self.execution_service = FakeExecutionService()
        self.evaluation_agent = FakeEvaluationAgent()
        self.runtime = FakeWorkflowRuntime()
        self.nodes = PostInterviewAssessmentNodes(
            message_repo=self.message_repo,
            evaluation_repo=self.evaluation_repo,
            summary_repo=self.summary_repo,
            execution_repo=self.execution_repo,
            plan_repo=self.plan_repo,
            session_repo=self.session_repo,
            execution_service=self.execution_service,
            evaluation_agent=self.evaluation_agent,
        )
        self.workflow = PostInterviewAssessmentWorkflow(self.nodes, runtime=self.runtime)

    async def test_workflow_generates_evaluation_and_persists_state(self):
        result = await self.workflow.run(self.session)

        self.assertEqual(result.evaluation.id, 900)
        self.assertEqual(result.state["workflow_run_id"], "assessment-run-1")
        self.assertEqual(result.state["thread_id"], "assessment:session-uid")
        self.assertEqual(result.state["branch"], "generated_evaluation")
        self.assertEqual(result.state["branch_reason"], "no_existing_evaluation")
        self.assertEqual(
            result.state["branch_decisions"],
            [
                {
                    "step_id": "ensure_evaluation",
                    "branch": "generated_evaluation",
                    "reason": "no_existing_evaluation",
                    "condition_checks": [
                        {
                            "name": "evaluation_exists",
                            "ok": False,
                            "value": None,
                            "detail": (
                                "No reusable evaluation artifact was found for this session."
                            ),
                        },
                        {
                            "name": "has_enough_transcript",
                            "ok": True,
                            "value": 1,
                            "detail": "Transcript contains enough user answers for evaluation.",
                        },
                    ],
                }
            ],
        )
        self.assertEqual(result.state["evaluation_id"], 900)
        self.assertEqual(result.state["evaluation_agent_run_id"], 801)
        self.assertEqual(result.state["status"], "success")
        self.assertIn("evaluation", result.state["completed_steps"])
        self.assertIn("ensure_evaluation", result.state["completed_steps"])
        self.assertEqual(
            result.state["output_contract_version"],
            "PostInterviewAssessmentOutput.v1",
        )
        self.assertEqual(
            result.state["outputs"]["artifacts"],
            [
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
        )
        self.assertEqual(self.runtime.saved[-1][1]["current_step"], "complete")
        self.assertEqual(self.runtime.saved[-1][1]["status"], "success")

    async def test_workflow_marks_partial_when_transcript_is_insufficient(self):
        self.nodes.message_repo = NoAnswerMessageRepo()

        result = await self.workflow.run(self.session)

        self.assertIsNone(result.evaluation)
        self.assertEqual(self.evaluation_repo.created, [])
        self.assertEqual(self.evaluation_agent.calls, [])
        self.assertEqual(result.state["status"], "partial")
        self.assertEqual(result.state["partial_reason"], "insufficient_transcript")
        self.assertEqual(result.state["branch"], "skip_evaluation_insufficient_transcript")
        self.assertEqual(result.state["branch_reason"], "insufficient_transcript")
        self.assertIn("evaluation", result.state["skipped_steps"])
        self.assertIn("ensure_evaluation", result.state["skipped_steps"])
        self.assertIn("complete", result.state["completed_steps"])
        self.assertEqual(
            result.state["branch_decisions"],
            [
                {
                    "step_id": "ensure_evaluation",
                    "branch": "skip_evaluation_insufficient_transcript",
                    "reason": "insufficient_transcript",
                    "condition_checks": [
                        {
                            "name": "evaluation_exists",
                            "ok": False,
                            "value": None,
                            "detail": (
                                "No reusable evaluation artifact was found for this session."
                            ),
                        },
                        {
                            "name": "has_enough_transcript",
                            "ok": False,
                            "value": 0,
                            "detail": (
                                "At least one user answer is required before generating "
                                "an interview evaluation."
                            ),
                        },
                    ],
                }
            ],
        )
        self.assertEqual(
            result.state["outputs"]["artifacts"],
            [
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
        )
        self.assertEqual(self.runtime.saved[-1][1]["current_step"], "complete")
        self.assertEqual(self.runtime.saved[-1][1]["status"], "partial")
        self.assertEqual(self.runtime.saved[-1][1]["state"]["status"], "partial")
        self.assertEqual(self.runtime.run_obj.workflow_id, "post_interview_assessment")
        self.assertEqual(self.runtime.run_obj.thread_id, "assessment:session-uid")
        self.assertEqual(self.session.status, "finished")
        self.assertEqual(self.execution_service.finished, [10])

    async def test_workflow_reuses_existing_evaluation(self):
        existing = evaluation(777, agent_run_id=333)
        self.evaluation_repo.existing = existing

        result = await self.workflow.run(self.session)

        self.assertIs(result.evaluation, existing)
        self.assertEqual(self.evaluation_repo.created, [])
        self.assertEqual(self.evaluation_agent.calls, [])
        self.assertEqual(result.state["branch"], "reuse_existing_evaluation")
        self.assertEqual(result.state["branch_reason"], "existing_evaluation_found")
        self.assertEqual(
            result.state["branch_decisions"],
            [
                {
                    "step_id": "ensure_evaluation",
                    "branch": "reuse_existing_evaluation",
                    "reason": "existing_evaluation_found",
                    "condition_checks": [
                        {
                            "name": "evaluation_exists",
                            "ok": True,
                            "value": 777,
                            "detail": (
                                "Latest evaluation artifact was found for this session."
                            ),
                        }
                    ],
                }
            ],
        )
        self.assertEqual(result.state["evaluation_id"], 777)
        self.assertEqual(result.state["evaluation_agent_run_id"], 333)
        self.assertIn("evaluation", result.state["completed_steps"])
        self.assertIn("ensure_evaluation_reused", result.state["completed_steps"])
        self.assertEqual(
            result.state["outputs"]["artifacts"],
            [
                {
                    "name": "evaluation",
                    "artifact_kind": "interview_evaluation",
                    "artifact_id": 777,
                    "source": "reused_existing_artifact",
                    "required": True,
                    "status": "available",
                    "reason": None,
                }
            ],
        )
        self.assertEqual(self.runtime.saved[-1][1]["status"], "success")

    async def test_workflow_marks_failure(self):
        self.nodes.evaluation_agent = FailingEvaluationAgent()

        with self.assertRaisesRegex(RuntimeError, "evaluation unavailable"):
            await self.workflow.run(self.session)

        failed_save = self.runtime.saved[-1][1]
        self.assertEqual(failed_save["current_step"], "ensure_evaluation")
        self.assertEqual(failed_save["status"], "failed")
        self.assertEqual(failed_save["state"]["status"], "failed")
        self.assertEqual(failed_save["last_error"]["step_id"], "ensure_evaluation")
        self.assertEqual(failed_save["last_error"]["message"], "evaluation unavailable")
        self.assertIn("ensure_evaluation", failed_save["state"]["failed_steps"])

    async def test_failed_retry_reuses_existing_evaluation(self):
        existing = evaluation(888, agent_run_id=444)
        self.evaluation_repo.existing = existing
        self.runtime.run_obj = SimpleNamespace(
            workflow_run_id="assessment-run-1",
            workflow_id="post_interview_assessment",
            thread_id="assessment:session-uid",
            project_id=1,
            session_id=10,
            status="failed",
            current_step="ensure_evaluation",
            state={
                "workflow_id": "post_interview_assessment",
                "workflow_run_id": "assessment-run-1",
                "thread_id": "assessment:session-uid",
                "status": "failed",
                "incoming_trigger": "interview_end",
                "completed_steps": ["load_assessment_context"],
                "failed_steps": ["ensure_evaluation"],
                "last_error": {
                    "step_id": "ensure_evaluation",
                    "message": "evaluation unavailable",
                },
            },
        )

        result = await self.workflow.run(self.session, incoming_trigger="manual_retry")

        start_state = self.runtime.saved[0][1]["state"]
        self.assertEqual(start_state["incoming_trigger"], "interview_end")
        self.assertEqual(start_state["resume_reason"], "failed_retry")
        self.assertEqual(start_state["resume_from_step"], "ensure_evaluation")
        self.assertEqual(start_state["failed_steps"], [])
        self.assertIsNone(start_state["last_error"])
        self.assertIsNone(start_state["branch"])
        self.assertIsNone(start_state["branch_reason"])
        self.assertEqual(start_state["branch_decisions"], [])
        self.assertIs(result.evaluation, existing)
        self.assertEqual(self.evaluation_agent.calls, [])
        self.assertEqual(result.state["branch"], "reuse_existing_evaluation")
        self.assertEqual(result.state["branch_reason"], "existing_evaluation_found")
        self.assertEqual(self.runtime.saved[-1][1]["status"], "success")

    async def test_record_project_outputs_updates_output_contract(self):
        result = await self.workflow.run(self.session)

        self.workflow.record_project_outputs(
            result,
            project_candidate_profile_id=501,
            resume_authenticity_report_id=601,
        )

        self.assertEqual(
            result.state["outputs"]["artifacts"],
            [
                {
                    "name": "evaluation",
                    "artifact_kind": "interview_evaluation",
                    "artifact_id": 900,
                    "source": "generated_by_workflow",
                    "required": True,
                    "status": "available",
                    "reason": None,
                },
                {
                    "name": "project_candidate_profile",
                    "artifact_kind": "project_candidate_profile",
                    "artifact_id": 501,
                    "source": "generated_after_assessment",
                    "required": False,
                    "status": "available",
                    "reason": None,
                },
                {
                    "name": "resume_authenticity",
                    "artifact_kind": "resume_authenticity_report",
                    "artifact_id": 601,
                    "source": "generated_after_assessment",
                    "required": False,
                    "status": "available",
                    "reason": None,
                },
            ],
        )
        self.assertEqual(
            result.state["next_actions"],
            [
                {
                    "type": "resume_optimization_ready",
                    "reason": "resume_authenticity_report_available",
                    "artifact_name": "resume_authenticity",
                }
            ],
        )
        self.assertEqual(result.state["outputs"]["next_actions"], result.state["next_actions"])
        self.assertEqual(self.runtime.saved[-1][1]["current_step"], "complete")
        self.assertEqual(self.runtime.saved[-1][1]["state"]["outputs"], result.state["outputs"])


if __name__ == "__main__":
    unittest.main()
