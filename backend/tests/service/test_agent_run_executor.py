import unittest
from types import SimpleNamespace

from service.support import configure_backend_imports

configure_backend_imports()

from app.service.agent_runtime_metrics import build_agent_runtime_metrics
from app.service.agent_run_service import AgentRunExecutor, AgentRunRecorder
from app.service.tool_calling_result import tool_calling_trace


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
        self.items = []

    def commit(self) -> None:
        self.commit_count += 1

    def add(self, item) -> None:
        self.items.append(item)

    def flush(self) -> None:
        if self.items and not getattr(self.items[-1], "id", None):
            self.items[-1].id = 900 + len(self.items)


class AgentRunExecutorTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.db = FakeDb()
        self.recorder = FakeRecorder()
        self.executor = AgentRunExecutor(db=self.db, recorder=self.recorder)

    def test_context_injects_evidence_packet_and_deduplicates_refs(self):
        evidence_packet = {
            "packet_id": "resume_rewrite_1_20260701000000",
            "task": "resume_rewrite",
            "evidence_items": [
                {
                    "evidence_id": "resume_claim_1",
                    "evidence_type": "resume_claim",
                    "source_type": "resume_profile",
                    "content_excerpt": "Built backend service.",
                },
                {
                    "evidence_id": "resume_claim_1",
                    "evidence_type": "resume_claim",
                    "source_type": "resume_profile",
                    "content_excerpt": "Built backend service.",
                },
                {
                    "evidence_id": "authenticity_check_1",
                    "evidence_type": "authenticity_check",
                    "source_type": "resume_authenticity_report",
                    "content_excerpt": "Claim supported.",
                },
            ],
            "missing_evidence": [],
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
        self.assertFalse(context.input_snapshot["evidence_packet_validation"]["ok"])
        self.assertIn(
            "Duplicate evidence_id: resume_claim_1",
            context.input_snapshot["evidence_packet_validation"]["errors"],
        )
        self.assertEqual(
            context.input_snapshot["evidence_packet_validation"]["metadata"]["evidence_types"],
            ["authenticity_check", "resume_claim"],
        )
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

    def test_context_injects_workflow_context(self):
        workflow_context = {
            "workflow_id": "interview_runtime",
            "workflow_run_id": "session_10_interview_runtime",
            "step_id": "followup",
        }

        context = self.executor.context(
            prompt_id="followup",
            project_id=1,
            session_id=10,
            input_snapshot={"answer_message_id": 100},
            workflow_context=workflow_context,
        )

        self.assertEqual(context.input_snapshot["workflow_context"], workflow_context)

    async def test_execute_spec_records_success_and_wraps_result(self):
        spec = self.executor.spec(
            prompt_id="followup",
            project_id=1,
            session_id=10,
            input_snapshot={"answer_message_id": 100},
            context_refs={"answer_message_id": 100},
            workflow_context={
                "workflow_id": "interview_runtime",
                "workflow_run_id": "session_10_interview_runtime",
                "step_id": "followup",
            },
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
        self.assertEqual(
            success_call["input_snapshot"]["workflow_context"]["workflow_id"],
            "interview_runtime",
        )
        self.assertEqual(success_call["model_name"], "test-model")
        self.assertEqual(success_call["output_snapshot"], {"reply": "next question"})
        self.assertEqual(success_call["raw_response"], {"raw": True})
        metrics = success_call["runtime_metrics"]
        self.assertEqual(metrics["status"], "success")
        self.assertGreaterEqual(metrics["latency_ms"], 0)
        self.assertEqual(metrics["tool_call_count"], 0)
        self.assertFalse(metrics["token_usage_available"])

    async def test_execute_spec_merges_tool_calling_outputs_into_evidence_packet(self):
        spec = self.executor.spec(
            prompt_id="followup",
            project_id=1,
            session_id=10,
            input_snapshot={"answer_message_id": 100},
            context_refs={"answer_message_id": 100},
            evidence_packet={
                "packet_id": "followup_10_20260702000000",
                "task": "followup_generation",
                "project_id": 1,
                "session_id": 10,
                "evidence_items": [
                    {
                        "evidence_id": "interview_answer_100",
                        "evidence_type": "interview_answer",
                        "source_type": "interview_message",
                        "source_id": 100,
                        "content_excerpt": "candidate answer",
                    }
                ],
                "missing_evidence": [],
            },
        )

        async def call():
            return "next question", {
                "tool_calling": {
                    "trace": [
                        {
                            "tool_call_id": "call_1",
                            "tool_name": "get_previous_answer",
                            "arguments": {"query": "Redis"},
                            "outputs": [
                                {
                                    "source_name": "previous_answer",
                                    "source_type": "interview_message",
                                    "source_id": 99,
                                    "content": "Previous Redis consistency answer",
                                    "score": 0.9,
                                    "metadata": {"round_no": 3},
                                }
                            ],
                        }
                    ]
                }
            }

        result = await self.executor.execute_spec(
            spec=spec,
            model_name="test-model",
            call=call,
        )

        self.assertIn("tool_get_previous_answer_interview_message_99", result.evidence_refs)
        success_call = self.recorder.success_calls[0]
        packet = success_call["input_snapshot"]["evidence_packet"]
        tool_items = [
            item
            for item in packet["evidence_items"]
            if item["evidence_id"] == "tool_get_previous_answer_interview_message_99"
        ]
        self.assertEqual(len(tool_items), 1)
        self.assertEqual(tool_items[0]["evidence_type"], "retrieved_knowledge")
        self.assertEqual(tool_items[0]["source_type"], "knowledge_source")
        self.assertEqual(tool_items[0]["metadata"]["tool_name"], "get_previous_answer")
        self.assertTrue(success_call["input_snapshot"]["evidence_packet_validation"]["ok"])
        metrics = success_call["runtime_metrics"]
        self.assertEqual(metrics["tool_call_count"], 1)
        self.assertEqual(metrics["tool_names"], ["get_previous_answer"])
        self.assertEqual(metrics["tool_error_count"], 0)

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
        metrics = failure_call["runtime_metrics"]
        self.assertEqual(metrics["status"], "failed")
        self.assertEqual(metrics["error_type"], "RuntimeError")
        self.assertGreaterEqual(metrics["latency_ms"], 0)

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


class ToolCallingResultTest(unittest.TestCase):
    def test_tool_calling_trace_reads_direct_and_wrapped_payloads(self):
        trace = [{"tool_name": "get_previous_answer"}, "ignored"]

        self.assertEqual(
            tool_calling_trace({"tool_calling": {"trace": trace}}),
            [{"tool_name": "get_previous_answer"}],
        )
        self.assertEqual(
            tool_calling_trace({"original": {"tool_calling": {"trace": trace}}}),
            [{"tool_name": "get_previous_answer"}],
        )


class AgentRuntimeMetricsTest(unittest.TestCase):
    def test_metrics_extract_tool_and_token_usage(self):
        raw_response = {
            "tool_calling": {
                "tool_budget_exhausted": True,
                "trace": [
                    {
                        "tool_name": "get_previous_answer",
                        "result": {"status": "success"},
                    },
                    {
                        "tool_name": "search_technology",
                        "result": {"status": "failed"},
                    },
                ],
                "responses": [
                    {
                        "usage": {
                            "prompt_tokens": 10,
                            "completion_tokens": 5,
                            "total_tokens": 15,
                        },
                        "choices": [
                            {
                                "message": {
                                    "tool_calls": [{"id": "call_1"}],
                                }
                            }
                        ],
                    },
                    {
                        "usage": {
                            "prompt_tokens": 8,
                            "completion_tokens": 6,
                            "total_tokens": 14,
                        },
                        "choices": [{"message": {"content": "final"}}],
                    },
                ],
            }
        }

        metrics = build_agent_runtime_metrics(
            raw_response=raw_response,
            latency_ms=42,
            status="success",
        )

        self.assertEqual(metrics["latency_ms"], 42)
        self.assertEqual(metrics["tool_call_count"], 2)
        self.assertEqual(metrics["tool_round_count"], 1)
        self.assertEqual(metrics["tool_names"], ["get_previous_answer", "search_technology"])
        self.assertEqual(metrics["tool_error_count"], 1)
        self.assertTrue(metrics["tool_budget_exhausted"])
        self.assertEqual(metrics["model_response_count"], 2)
        self.assertTrue(metrics["token_usage_available"])
        self.assertEqual(metrics["token_usage"]["prompt_tokens"], 18)
        self.assertEqual(metrics["token_usage"]["completion_tokens"], 11)
        self.assertEqual(metrics["token_usage"]["total_tokens"], 29)
        self.assertEqual(metrics["token_usage"]["source_count"], 2)


class AgentRunRecorderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = FakeDb()
        self.recorder = AgentRunRecorder(self.db)
        self.definition = AgentRunExecutor(self.db).definition("resume_rewrite")

    def test_record_success_adds_agent_definition_validation(self):
        item = self.recorder.record_success(
            definition=self.definition,
            project_id=1,
            session_id=None,
            input_snapshot={
                "resume_id": 7,
                "resume_profile": {"name": "Lynn"},
                "workflow_context": {
                    "workflow_id": "resume_optimization",
                    "workflow_run_id": "project_1_resume_optimization",
                    "step_id": "resume_rewrite",
                },
            },
            context_refs={"resume_id": 7, "resume_profile_id": 8},
            evidence_refs=["resume_claim_1", "authenticity_check_1"],
            output_snapshot={"rewritten_resume": "ok"},
            raw_response={"raw": True},
            model_name="test-model",
            runtime_metrics={
                "status": "success",
                "latency_ms": 12,
                "tool_call_count": 0,
            },
        )

        self.assertEqual(item.input_snapshot["runtime_metrics"]["latency_ms"], 12)
        validation = item.input_snapshot["agent_definition_validation"]
        workflow_validation = item.input_snapshot["workflow_context_validation"]
        self.assertTrue(validation["ok"])
        self.assertTrue(workflow_validation["ok"])
        self.assertEqual(validation["errors"], [])
        self.assertEqual(workflow_validation["errors"], [])
        self.assertEqual(workflow_validation["metadata"]["workflow_id"], "resume_optimization")
        self.assertEqual(validation["metadata"]["agent_name"], "ResumeRewriteAgent")
        self.assertEqual(validation["metadata"]["prompt_id"], "resume_rewrite")
        self.assertEqual(validation["metadata"]["task_name"], "resume_rewrite")
        self.assertEqual(validation["metadata"]["prompt_version"], "3.0.0")
        self.assertEqual(item.agent_name, "ResumeRewriteAgent")
        self.assertEqual(item.prompt_id, "resume_rewrite")
        self.assertEqual(item.task_name, "resume_rewrite")

    def test_record_success_persists_evidence_items(self):
        item = self.recorder.record_success(
            definition=self.definition,
            project_id=1,
            session_id=None,
            input_snapshot={
                "resume_id": 7,
                "workflow_context": {
                    "workflow_id": "resume_optimization",
                    "workflow_run_id": "project_1_resume_optimization",
                    "step_id": "resume_rewrite",
                },
                "evidence_packet": {
                    "packet_id": "resume_rewrite_1_20260702000000",
                    "task": "resume_rewrite",
                    "evidence_items": [
                        {
                            "evidence_id": "resume_claim_1",
                            "evidence_type": "resume_claim",
                            "source_type": "resume_profile",
                            "source_id": 8,
                            "project_id": 1,
                            "content_excerpt": "Built backend service.",
                            "tags": ["project"],
                            "confidence": "claim_only",
                            "metadata": {"project_name": "Risk"},
                        },
                        {
                            "evidence_id": "resume_claim_1",
                            "evidence_type": "resume_claim",
                            "source_type": "resume_profile",
                            "content_excerpt": "Duplicate ref.",
                        },
                        {
                            "evidence_id": "unused_ref",
                            "evidence_type": "resume_claim",
                            "source_type": "resume_profile",
                            "content_excerpt": "Not present in evidence_refs.",
                        },
                    ],
                    "missing_evidence": [],
                },
            },
            context_refs={"resume_id": 7, "resume_profile_id": 8},
            evidence_refs=["resume_claim_1"],
            output_snapshot={"rewritten_resume": "ok"},
            raw_response={"raw": True},
            model_name="test-model",
        )

        evidence_items = [
            stored
            for stored in self.db.items
            if getattr(stored, "evidence_id", None) == "resume_claim_1"
        ]
        self.assertEqual(len(evidence_items), 1)
        stored = evidence_items[0]
        self.assertEqual(stored.agent_run_id, item.id)
        self.assertEqual(stored.evidence_id, "resume_claim_1")
        self.assertEqual(stored.evidence_type, "resume_claim")
        self.assertEqual(stored.source_type, "resume_profile")
        self.assertEqual(stored.source_id, 8)
        self.assertEqual(stored.project_id, 1)
        self.assertEqual(stored.prompt_id, "resume_rewrite")
        self.assertEqual(stored.workflow_id, "resume_optimization")
        self.assertEqual(stored.workflow_run_id, "project_1_resume_optimization")
        self.assertEqual(stored.step_id, "resume_rewrite")
        self.assertEqual(stored.content_excerpt, "Built backend service.")
        self.assertEqual(stored.tags, ["project"])
        self.assertEqual(stored.confidence, "claim_only")
        self.assertEqual(stored.item_metadata, {"project_name": "Risk"})

    def test_record_failure_also_adds_agent_definition_validation(self):
        item = self.recorder.record_failure(
            definition=self.definition,
            project_id=1,
            session_id=None,
            input_snapshot={"resume_id": 7},
            context_refs={"resume_id": 7},
            evidence_refs=[],
            error=RuntimeError("model unavailable"),
            model_name="test-model",
            runtime_metrics={
                "status": "failed",
                "latency_ms": 7,
                "error_type": "RuntimeError",
            },
        )

        self.assertEqual(item.input_snapshot["runtime_metrics"]["status"], "failed")
        self.assertEqual(item.input_snapshot["runtime_metrics"]["latency_ms"], 7)
        self.assertFalse(item.input_snapshot["prompt_contract_validation"]["ok"])
        self.assertTrue(item.input_snapshot["agent_definition_validation"]["ok"])
        self.assertTrue(item.input_snapshot["workflow_context_validation"]["ok"])
        self.assertIn(
            "Workflow context is not provided",
            item.input_snapshot["workflow_context_validation"]["warnings"],
        )
        self.assertEqual(item.status, "failed")
        self.assertEqual(item.error_message, "model unavailable")


if __name__ == "__main__":
    unittest.main()
