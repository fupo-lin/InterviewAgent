import unittest
from types import SimpleNamespace

from service.support import configure_backend_imports

configure_backend_imports()

from app.service.interview_workflow_task import InterviewWorkflowTaskService


class FakeSessionRepo:
    def __init__(self, db):
        self.db = db

    def get_by_uid(self, session_uid):
        return self.db.session


class FakeWorkflowRepo:
    def __init__(self, db):
        self.db = db

    def get_by_thread_id(self, thread_id):
        return self.db.workflow_run

    def create(self, **kwargs):
        self.db.workflow_run = SimpleNamespace(
            id=1,
            **kwargs,
        )
        self.db.workflow_run.workflow_run_id = "interview_runtime_abc"
        return self.db.workflow_run

    def save_state(self, item, **kwargs):
        for key, value in kwargs.items():
            setattr(item, key, value)
        self.db.saved.append(kwargs)
        return item


class FakeDb:
    def __init__(self):
        self.session = SimpleNamespace(
            id=10,
            session_uid="session-uid",
            project_id=20,
            role_name="Backend Engineer",
            interview_plan_id=30,
            status="active",
        )
        self.workflow_run = None
        self.saved = []
        self.commits = 0

    def commit(self):
        self.commits += 1


class InterviewWorkflowTaskTest(unittest.TestCase):
    def test_enqueue_creates_queued_workflow_task_without_executing_steps(self):
        db = FakeDb()
        service = InterviewWorkflowTaskService(
            db,
            session_repo=FakeSessionRepo(db),
            workflow_repo=FakeWorkflowRepo(db),
        )

        task = service.enqueue_user_message("session-uid", "candidate answer")

        self.assertEqual(task.workflow_run_id, "interview_runtime_abc")
        self.assertEqual(task.status, "queued")
        self.assertEqual(db.workflow_run.status, "queued")
        self.assertEqual(db.workflow_run.current_step, "workflow_task")
        self.assertEqual(db.workflow_run.state["task"]["status"], "queued")
        self.assertEqual(db.workflow_run.state["incoming_user_input"], "candidate answer")
        self.assertEqual(db.commits, 1)

    def test_enqueue_failed_workflow_preserves_interrupted_input_for_retry(self):
        db = FakeDb()
        db.workflow_run = SimpleNamespace(
            id=1,
            workflow_run_id="interview_runtime_failed",
            workflow_id="interview_runtime",
            thread_id="interview:session-uid",
            project_id=20,
            session_id=10,
            status="failed",
            current_step="generate_followup",
            last_error={"step_id": "generate_followup", "message": "failed"},
            error_message="failed",
            state={
                "workflow_id": "interview_runtime",
                "thread_id": "interview:session-uid",
                "status": "failed",
                "incoming_user_input": "original answer",
                "completed_steps": ["save_user_answer"],
                "failed_steps": ["generate_followup"],
                "last_error": {"step_id": "generate_followup", "message": "failed"},
            },
        )
        service = InterviewWorkflowTaskService(
            db,
            session_repo=FakeSessionRepo(db),
            workflow_repo=FakeWorkflowRepo(db),
        )

        task = service.enqueue_user_message("session-uid", "new answer")

        self.assertEqual(task.workflow_run_id, "interview_runtime_failed")
        self.assertEqual(task.status, "queued_retry")
        self.assertEqual(db.workflow_run.state["incoming_user_input"], "original answer")
        self.assertEqual(db.workflow_run.state["task"]["status"], "queued_retry")
        self.assertEqual(db.workflow_run.status, "failed")
        self.assertEqual(db.commits, 1)


if __name__ == "__main__":
    unittest.main()
