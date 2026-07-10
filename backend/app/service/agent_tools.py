from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from app.service.retrieval_contract import RetrievedKnowledge


@dataclass(frozen=True)
class ToolExecutionContext:
    session: object
    answer_message: object | None = None
    current_section: dict | None = None
    execution: object | None = None

    @property
    def project_id(self) -> int | None:
        return getattr(self.session, "project_id", None) if self.session else None

    @property
    def session_id(self) -> int | None:
        return getattr(self.session, "id", None) if self.session else None


@dataclass(frozen=True)
class ToolCall:
    tool_name: str
    query: str | None = None
    args: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "query": self.query,
            "args": self.args,
        }


@dataclass(frozen=True)
class ToolPlanningContext:
    task_name: str
    session: object
    answer_message: object | None = None
    current_section: dict | None = None
    execution: object | None = None

    @property
    def project_id(self) -> int | None:
        return getattr(self.session, "project_id", None) if self.session else None

    @property
    def answer_text(self) -> str:
        return getattr(self.answer_message, "content", "") if self.answer_message else ""


@dataclass(frozen=True)
class ToolPolicy:
    task_name: str
    tool_names: tuple[str, ...]
    requires_project: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    handler: Callable[[ToolExecutionContext, ToolCall], list[RetrievedKnowledge]]
    evidence_source: str = "knowledge_source"


@dataclass(frozen=True)
class ToolResult:
    tool_name: str
    status: str
    outputs: list[RetrievedKnowledge] = field(default_factory=list)
    error_message: str | None = None
    latency_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "status": self.status,
            "output_count": len(self.outputs),
            "error_message": self.error_message,
            "latency_ms": self.latency_ms,
            "metadata": self.metadata,
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        self._definitions[definition.name] = definition

    def get(self, name: str) -> ToolDefinition:
        try:
            return self._definitions[name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool: {name}") from exc

    def all(self) -> list[ToolDefinition]:
        return list(self._definitions.values())


class ToolPlanner:
    def __init__(self, policies: list[ToolPolicy] | None = None) -> None:
        self.policies = {policy.task_name: policy for policy in policies or []}

    def plan(self, context: ToolPlanningContext) -> list[ToolCall]:
        policy = self.policies.get(context.task_name)
        if not policy:
            return []

        calls = []
        for tool_name in policy.tool_names:
            if tool_name in policy.requires_project and not context.project_id:
                continue
            calls.append(
                ToolCall(
                    tool_name=tool_name,
                    query=self._query_for(tool_name, context),
                    args=self._args_for(tool_name, context),
                )
            )
        return calls

    def _query_for(self, tool_name: str, context: ToolPlanningContext) -> str | None:
        if tool_name == "get_resume_profile":
            return ""
        return context.answer_text

    def _args_for(self, tool_name: str, context: ToolPlanningContext) -> dict[str, Any]:
        if tool_name == "get_previous_answer":
            return {"limit": 4}
        if tool_name in {"search_company_info", "search_technology"}:
            return {"limit": 5}
        return {}


class ToolRuntime:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def execute(
        self,
        calls: list[ToolCall],
        context: ToolExecutionContext,
    ) -> list[ToolResult]:
        results = []
        for call in calls:
            results.append(self.execute_one(call, context))
        return results

    def execute_one(
        self,
        call: ToolCall,
        context: ToolExecutionContext,
    ) -> ToolResult:
        started = perf_counter()
        try:
            definition = self.registry.get(call.tool_name)
            outputs = definition.handler(context, call)
        except Exception as exc:
            return ToolResult(
                tool_name=call.tool_name,
                status="failed",
                error_message=str(exc),
                latency_ms=self._latency_ms(started),
                metadata={
                    "executed_at": self._timestamp(),
                    "error_type": exc.__class__.__name__,
                },
            )
        return ToolResult(
            tool_name=call.tool_name,
            status="success",
            outputs=self._annotate_outputs(call, outputs),
            latency_ms=self._latency_ms(started),
            metadata={"executed_at": self._timestamp()},
        )

    def _annotate_outputs(
        self,
        call: ToolCall,
        outputs: list[RetrievedKnowledge],
    ) -> list[RetrievedKnowledge]:
        annotated = []
        for item in outputs:
            metadata = dict(item.metadata or {})
            metadata["tool_name"] = call.tool_name
            metadata["tool_query"] = call.query
            annotated.append(
                RetrievedKnowledge(
                    source_name=item.source_name,
                    source_type=item.source_type,
                    source_id=item.source_id,
                    content=item.content,
                    score=item.score,
                    metadata=metadata,
                )
            )
        return annotated

    def _latency_ms(self, started: float) -> int:
        return int((perf_counter() - started) * 1000)

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()


def build_interview_tool_runtime(retriever) -> ToolRuntime:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="get_resume_profile",
            description="Load the latest structured resume profile for the preparation project.",
            handler=lambda context, call: retriever.get_resume_profile(context.project_id),
        )
    )
    registry.register(
        ToolDefinition(
            name="get_previous_answer",
            description="Retrieve previous interview answers relevant to the current answer.",
            handler=lambda context, call: retriever.get_previous_answer(
                session_id=context.session_id,
                query=call.query,
                limit=call.args.get("limit", 4),
            )
            if context.session_id
            else [],
        )
    )
    registry.register(
        ToolDefinition(
            name="search_company_info",
            description="Search local company and JD knowledge attached to the project.",
            handler=lambda context, call: retriever.search_company_info(
                project_id=context.project_id,
                query=call.query,
                limit=call.args.get("limit", 5),
            ),
        )
    )
    registry.register(
        ToolDefinition(
            name="search_technology",
            description="Search local technology evidence from resume, JD, gap, and candidate profile artifacts.",
            handler=lambda context, call: retriever.search_technology(
                project_id=context.project_id,
                query=call.query,
                limit=call.args.get("limit", 5),
            ),
        )
    )
    return ToolRuntime(registry)


def build_interview_tool_planner() -> ToolPlanner:
    return ToolPlanner(
        policies=[
            ToolPolicy(
                task_name="followup_generation",
                tool_names=(
                    "get_previous_answer",
                    "get_resume_profile",
                    "search_technology",
                ),
                requires_project=("get_resume_profile", "search_technology"),
            ),
            ToolPolicy(
                task_name="topic_completion_judge",
                tool_names=(
                    "get_previous_answer",
                    "search_technology",
                ),
                requires_project=("search_technology",),
            ),
        ]
    )
