import unittest
from types import SimpleNamespace

from service.support import configure_backend_imports

configure_backend_imports()

from app.service.workflow_runtime import WorkflowRuntime


class FakeWorkflowRunRepository:
    def __init__(self) -> None:
        self.by_thread_id = {}
        self.created = []
        self.saved = []

    def get_by_thread_id(self, thread_id):
        return self.by_thread_id.get(thread_id)

    def create(self, **kwargs):
        item = SimpleNamespace(id=len(self.created) + 1, **kwargs)
        self.created.append(item)
        self.by_thread_id[item.thread_id] = item
        return item

    def save_state(self, item, **kwargs):
        for key, value in kwargs.items():
            setattr(item, key, value)
        self.saved.append((item, kwargs))
        return item


class WorkflowRuntimeTest(unittest.TestCase):
    def test_load_or_create_creates_workflow_run(self):
        repo = FakeWorkflowRunRepository()
        runtime = WorkflowRuntime(repo)

        item = runtime.load_or_create(
            workflow_id="interview_runtime",
            thread_id="interview:abc",
            project_id=1,
            session_id=10,
            initial_state={"thread_id": "interview:abc"},
        )

        self.assertEqual(item.workflow_id, "interview_runtime")
        self.assertEqual(item.thread_id, "interview:abc")
        self.assertEqual(item.project_id, 1)
        self.assertEqual(item.session_id, 10)
        self.assertEqual(item.status, "running")
        self.assertEqual(item.current_step, "start")
        self.assertEqual(item.state, {"thread_id": "interview:abc"})
        self.assertTrue(item.workflow_run_id.startswith("interview_runtime_"))

    def test_load_or_create_reuses_existing_thread(self):
        repo = FakeWorkflowRunRepository()
        runtime = WorkflowRuntime(repo)
        existing = SimpleNamespace(
            workflow_run_id="existing",
            workflow_id="interview_runtime",
            thread_id="interview:abc",
            state={"status": "waiting_user"},
        )
        repo.by_thread_id["interview:abc"] = existing

        item = runtime.load_or_create(
            workflow_id="interview_runtime",
            thread_id="interview:abc",
            project_id=1,
            session_id=10,
            initial_state={},
        )

        self.assertIs(item, existing)
        self.assertEqual(repo.created, [])

    def test_save_persists_state_and_status(self):
        repo = FakeWorkflowRunRepository()
        runtime = WorkflowRuntime(repo)
        item = SimpleNamespace()

        runtime.save(
            item,
            state={"status": "waiting_user"},
            current_step="wait_user_answer",
            status="waiting_user",
            last_error=None,
        )

        self.assertEqual(item.state, {"status": "waiting_user"})
        self.assertEqual(item.current_step, "wait_user_answer")
        self.assertEqual(item.status, "waiting_user")
        self.assertIsNone(item.last_error)
        self.assertIsNone(item.error_message)


if __name__ == "__main__":
    unittest.main()
