import unittest
from types import SimpleNamespace

from service.support import configure_backend_imports

configure_backend_imports()

from app.service.agent_tools import (
    ToolCall,
    ToolDefinition,
    ToolExecutionContext,
    ToolPlanningContext,
    ToolRegistry,
    ToolRuntime,
    build_interview_tool_planner,
    build_interview_tool_runtime,
)
from app.service.retrieval_contract import RetrievedKnowledge


class FakeRetriever:
    def get_resume_profile(self, project_id):
        return [
            RetrievedKnowledge(
                source_name="resume_profile",
                source_type="resume_profile",
                source_id=1,
                content="Redis project",
                score=1.0,
            )
        ]

    def get_previous_answer(self, session_id, query=None, limit=4):
        return [
            RetrievedKnowledge(
                source_name="previous_answer",
                source_type="interview_message",
                source_id=2,
                content=f"previous: {query}",
                score=0.8,
            )
        ]

    def search_company_info(self, project_id, query=None, limit=5):
        return []

    def search_technology(self, project_id, query=None, limit=5):
        return [
            RetrievedKnowledge(
                source_name="technology",
                source_type="resume_profile",
                source_id=3,
                content="Redis MySQL",
                score=0.9,
            )
        ]


class AgentToolsTest(unittest.TestCase):
    def test_tool_runtime_executes_registered_tool_and_annotates_output(self):
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="custom_tool",
                description="custom",
                handler=lambda context, call: [
                    RetrievedKnowledge(
                        source_name="custom",
                        source_type="custom_source",
                        source_id=10,
                        content=call.query or "",
                    )
                ],
            )
        )
        runtime = ToolRuntime(registry)

        result = runtime.execute_one(
            ToolCall(tool_name="custom_tool", query="hello"),
            ToolExecutionContext(session=SimpleNamespace(id=1, project_id=2)),
        )

        self.assertEqual(result.status, "success")
        self.assertEqual(result.outputs[0].metadata["tool_name"], "custom_tool")
        self.assertEqual(result.outputs[0].metadata["tool_query"], "hello")

    def test_tool_runtime_records_tool_failure_without_raising(self):
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="broken_tool",
                description="broken",
                handler=lambda context, call: (_ for _ in ()).throw(RuntimeError("boom")),
            )
        )
        runtime = ToolRuntime(registry)

        result = runtime.execute_one(
            ToolCall(tool_name="broken_tool"),
            ToolExecutionContext(session=SimpleNamespace(id=1, project_id=2)),
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_message, "boom")
        self.assertEqual(result.outputs, [])

    def test_interview_tool_runtime_registers_core_rag_tools(self):
        runtime = build_interview_tool_runtime(FakeRetriever())
        context = ToolExecutionContext(session=SimpleNamespace(id=10, project_id=20))

        results = runtime.execute(
            [
                ToolCall(tool_name="get_resume_profile"),
                ToolCall(tool_name="get_previous_answer", query="Redis"),
                ToolCall(tool_name="search_technology", query="Redis"),
            ],
            context,
        )

        self.assertEqual([item.status for item in results], ["success", "success", "success"])
        self.assertEqual([item.tool_name for item in results], [
            "get_resume_profile",
            "get_previous_answer",
            "search_technology",
        ])
        self.assertGreaterEqual(sum(len(item.outputs) for item in results), 3)

    def test_interview_tool_planner_uses_task_policy(self):
        planner = build_interview_tool_planner()

        calls = planner.plan(
            ToolPlanningContext(
                task_name="followup_generation",
                session=SimpleNamespace(id=10, project_id=20),
                answer_message=SimpleNamespace(content="Redis latency"),
            )
        )

        self.assertEqual(
            [item.tool_name for item in calls],
            ["get_previous_answer", "get_resume_profile", "search_technology"],
        )
        self.assertEqual(calls[0].query, "Redis latency")

    def test_interview_tool_planner_skips_project_tools_without_project(self):
        planner = build_interview_tool_planner()

        calls = planner.plan(
            ToolPlanningContext(
                task_name="followup_generation",
                session=SimpleNamespace(id=10, project_id=None),
                answer_message=SimpleNamespace(content="Redis latency"),
            )
        )

        self.assertEqual([item.tool_name for item in calls], ["get_previous_answer"])


if __name__ == "__main__":
    unittest.main()
