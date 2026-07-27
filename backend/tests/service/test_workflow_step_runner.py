import asyncio
import unittest

from service.support import configure_backend_imports

configure_backend_imports()

from app.service.workflow_step_runner import WorkflowStepRunner, WorkflowStepTimeoutError


class WorkflowStepRunnerTest(unittest.IsolatedAsyncioTestCase):
    async def test_retries_failed_step_and_records_attempts(self):
        runner = WorkflowStepRunner()
        state = {}
        calls = []

        async def flaky():
            calls.append("call")
            if len(calls) == 1:
                raise RuntimeError("temporary failure")
            return "ok"

        result = await runner.run(state, "generate_followup", flaky, max_attempts=2)

        self.assertEqual(result, "ok")
        self.assertEqual(calls, ["call", "call"])
        self.assertEqual(state["step_execution"]["generate_followup"]["status"], "success")
        self.assertEqual(state["step_execution"]["generate_followup"]["attempts"], 2)
        self.assertNotIn("retrying_step", state)

    async def test_timeout_records_failure(self):
        runner = WorkflowStepRunner()
        state = {}

        async def slow():
            await asyncio.sleep(0.05)

        with self.assertRaises(WorkflowStepTimeoutError):
            await runner.run(
                state,
                "slow_step",
                slow,
                timeout_seconds=0.001,
                max_attempts=1,
            )

        self.assertEqual(state["step_execution"]["slow_step"]["status"], "failed")
        self.assertEqual(
            state["step_execution"]["slow_step"]["last_error"]["error_type"],
            "WorkflowStepTimeoutError",
        )


if __name__ == "__main__":
    unittest.main()
