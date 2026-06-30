import unittest
from types import SimpleNamespace

from service.support import configure_backend_imports

configure_backend_imports()

from app.service.agent_run_service import AgentRunExecutor


class FakeRecorder:
    def __init__(self) -> None:
        self.success_calls = []
        self.failure_calls = []

    def record_success(self, **kwargs):
        self.success_calls.append(kwargs)
        return SimpleNamespace(id=501)

    def record_failure(self, **kwargs):
        self.failure_calls.append(kwargs)
        return SimpleNamespace(id=502)


class FakeDb:
    def __init__(self) -> None:
        self.commit_count = 0

    def commit(self) -> None:
        self.commit_count += 1


class AgentRunExecutorTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.db = FakeDb()
        self.recorder = FakeRecorder()
        self.executor = AgentRunExecutor(db=self.db, recorder=self.recorder)

    def test_context_injects_evidence_packet_and_deduplicates_refs(self):
        evidence_packet = {
            "evidence_items": [
                {"evidence_id": "resume_claim_1", "evidence_type": "resume_claim"},
                {"evidence_id": "resume_claim_1", "evidence_type": "resume_claim"},
                {"evidence_id": "authenticity_check_1", "evidence_type": "authenticity_check"},
            ]
        }

        context = self.executor.context(
            prompt_id="resume_rewrite",
            project_id=1,
            session_id=None,
            input_snapshot={"resume_id": 7},
            context_refs={"resume_profile_id": 8},
            evidence_packet=evidence_packet,
        )

        self.assertEqual(context.definition.prompt_id, "resume_rewrite")
        self.assertEqual(context.input_snapshot["resume_id"], 7)
        self.assertIs(context.input_snapshot["evidence_packet"], evidence_packet)
        self.assertEqual(context.context_refs, {"resume_profile_id": 8})
        self.assertEqual(context.evidence_refs, ["resume_claim_1", "authenticity_check_1"])

    def test_context_keeps_explicit_evidence_refs(self):
        context = self.executor.context(
            prompt_id="followup",
            project_id=1,
            session_id=10,
            input_snapshot={"answer_message_id": 100},
            evidence_packet={
                "evidence_items": [
                    {"evidence_id": "interview_answer_100", "evidence_type": "interview_answer"},
                ]
            },
            evidence_refs=["manual_ref"],
        )

        self.assertEqual(context.evidence_refs, ["manual_ref"])

    async def test_execute_spec_records_success_and_wraps_result(self):
        spec = self.executor.spec(
            prompt_id="followup",
            project_id=1,
            session_id=10,
            input_snapshot={"answer_message_id": 100},
            context_refs={"answer_message_id": 100},
            evidence_packet={
                "evidence_items": [
                    {"evidence_id": "interview_answer_100", "evidence_type": "interview_answer"},
                ]
            },
            output_snapshot=lambda output: {"reply": output},
        )

        async def call():
            return "next question", {"raw": True}

        result = await self.executor.execute_spec(
            spec=spec,
            model_name="test-model",
            call=call,
        )

        self.assertEqual(result.output, "next question")
        self.assertEqual(result.raw_response, {"raw": True})
        self.assertEqual(result.agent_run.id, 501)
        self.assertEqual(result.output_schema, "InterviewQuestion.v1")
        self.assertEqual(result.evidence_refs, ["interview_answer_100"])
        self.assertEqual(
            result.message_fields(),
            {
                "content": "next question",
                "raw_response": {"raw": True},
                "agent_run_id": 501,
                "schema_version": "InterviewQuestion.v1",
                "evidence_refs": ["interview_answer_100"],
            },
        )
        self.assertEqual(len(self.recorder.success_calls), 1)
        success_call = self.recorder.success_calls[0]
        self.assertEqual(success_call["definition"].prompt_id, "followup")
        self.assertEqual(success_call["model_name"], "test-model")
        self.assertEqual(success_call["output_snapshot"], {"reply": "next question"})
        self.assertEqual(success_call["raw_response"], {"raw": True})

    async def test_execute_spec_records_failure_and_honors_commit_on_failure(self):
        spec = self.executor.spec(
            prompt_id="followup",
            project_id=1,
            session_id=10,
            input_snapshot={"answer_message_id": 100},
            commit_on_failure=True,
        )

        async def call():
            raise RuntimeError("model unavailable")

        with self.assertRaisesRegex(RuntimeError, "model unavailable"):
            await self.executor.execute_spec(
                spec=spec,
                model_name="test-model",
                call=call,
            )

        self.assertEqual(self.db.commit_count, 1)
        self.assertEqual(len(self.recorder.failure_calls), 1)
        failure_call = self.recorder.failure_calls[0]
        self.assertEqual(failure_call["definition"].prompt_id, "followup")
        self.assertEqual(str(failure_call["error"]), "model unavailable")
        self.assertEqual(failure_call["model_name"], "test-model")

    async def test_execute_spec_can_skip_failure_commit(self):
        spec = self.executor.spec(
            prompt_id="followup",
            project_id=1,
            session_id=10,
            input_snapshot={"answer_message_id": 100},
            commit_on_failure=False,
        )

        async def call():
            raise RuntimeError("parse failed")

        with self.assertRaisesRegex(RuntimeError, "parse failed"):
            await self.executor.execute_spec(
                spec=spec,
                model_name="test-model",
                call=call,
            )

        self.assertEqual(self.db.commit_count, 0)
        self.assertEqual(len(self.recorder.failure_calls), 1)


if __name__ == "__main__":
    unittest.main()
