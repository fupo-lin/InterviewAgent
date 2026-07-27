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
    parameters: dict[str, Any] = field(default_factory=dict)
    evidence_source: str = "knowledge_source"
    side_effect_level: str = "read"
    requires_project: bool = False

    def openai_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
                or {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
        }


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

    def allowed_tool_names(self, task_name: str, project_id: int | None = None) -> tuple[str, ...]:
        policy = self.policies.get(task_name)
        if not policy:
            return ()
        return tuple(
            tool_name
            for tool_name in policy.tool_names
            if tool_name not in policy.requires_project or project_id
        )

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
        self.allowed_side_effect_levels = {"read"}

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
        allowed_tool_names: tuple[str, ...] | list[str] | set[str] | None = None,
        allowed_side_effect_levels: tuple[str, ...] | list[str] | set[str] | None = None,
    ) -> ToolResult:
        started = perf_counter()
        try:
            definition = self.registry.get(call.tool_name)
            self._authorize(
                definition=definition,
                call=call,
                context=context,
                allowed_tool_names=allowed_tool_names,
                allowed_side_effect_levels=allowed_side_effect_levels,
            )
            call = self._validated_call(definition, call)
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

    def _authorize(
        self,
        *,
        definition: ToolDefinition,
        call: ToolCall,
        context: ToolExecutionContext,
        allowed_tool_names: tuple[str, ...] | list[str] | set[str] | None,
        allowed_side_effect_levels: tuple[str, ...] | list[str] | set[str] | None,
    ) -> None:
        allowed_tools = set(allowed_tool_names or [])
        if allowed_tools and call.tool_name not in allowed_tools:
            raise PermissionError(f"Tool not allowed in this node: {call.tool_name}")
        allowed_effects = set(allowed_side_effect_levels or self.allowed_side_effect_levels)
        if definition.side_effect_level not in allowed_effects:
            raise PermissionError(
                f"Tool side effect level not allowed: {definition.side_effect_level}"
            )
        if definition.requires_project and not context.project_id:
            raise PermissionError(f"Tool requires project context: {definition.name}")

    def _validated_call(self, definition: ToolDefinition, call: ToolCall) -> ToolCall:
        schema = definition.parameters or {}
        properties = schema.get("properties") or {}
        args = dict(call.args or {})
        query = call.query
        if "query" in properties and (query is None or not str(query).strip()):
            if "query" in schema.get("required", []):
                raise ValueError(f"Tool requires query: {definition.name}")
        for key, property_schema in properties.items():
            if key == "query" or key not in args:
                continue
            if property_schema.get("type") == "integer":
                args[key] = self._bounded_int(
                    args[key],
                    minimum=property_schema.get("minimum"),
                    maximum=property_schema.get("maximum"),
                    default=property_schema.get("default"),
                )
        if schema.get("additionalProperties") is False:
            args = {key: value for key, value in args.items() if key in properties}
        return ToolCall(tool_name=call.tool_name, query=query, args=args)

    def _bounded_int(self, value, *, minimum=None, maximum=None, default=None) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = int(default or minimum or 0)
        if minimum is not None:
            parsed = max(parsed, int(minimum))
        if maximum is not None:
            parsed = min(parsed, int(maximum))
        return parsed

    def openai_tool_schemas(
        self,
        allowed_tool_names: tuple[str, ...] | list[str] | None = None,
    ) -> list[dict[str, Any]]:
        allowed = set(allowed_tool_names or [])
        definitions = self.registry.all()
        if allowed:
            definitions = [
                definition
                for definition in definitions
                if definition.name in allowed
            ]
        return [definition.openai_tool_schema() for definition in definitions]

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
            description=(
                "Use when the next interview question needs factual context from the "
                "candidate resume or project profile. Do not use for interview transcript "
                "history. Requires a project_id from the current session."
            ),
            handler=lambda context, call: retriever.get_resume_profile(context.project_id),
            requires_project=True,
            parameters={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        )
    )
    registry.register(
        ToolDefinition(
            name="get_previous_answer",
            description=(
                "Use before judging coverage or asking a follow-up when the candidate may "
                "have already mentioned relevant details earlier in this interview. The "
                "query should describe the technical point, claim, or missing detail to verify."
            ),
            handler=lambda context, call: retriever.get_previous_answer(
                session_id=context.session_id,
                query=call.query,
                limit=call.args.get("limit", 4),
            )
            if context.session_id
            else [],
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Technical topic, candidate claim, or follow-up gap to search for.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of previous answers to return.",
                        "minimum": 1,
                        "maximum": 8,
                        "default": 4,
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        )
    )
    registry.register(
        ToolDefinition(
            name="search_company_info",
            description=(
                "Use when a follow-up should be grounded in local job description, company, "
                "or role requirements attached to the preparation project. Do not use for "
                "candidate answer history."
            ),
            handler=lambda context, call: retriever.search_company_info(
                project_id=context.project_id,
                query=call.query,
                limit=call.args.get("limit", 5),
            ),
            requires_project=True,
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Role, responsibility, company, or JD requirement to search for.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of knowledge items to return.",
                        "minimum": 1,
                        "maximum": 8,
                        "default": 5,
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        )
    )
    registry.register(
        ToolDefinition(
            name="search_technology",
            description=(
                "Use when you need technical evidence from resume, JD, gap analysis, or "
                "candidate profile artifacts to make the next question more specific. "
                "Prefer this over guessing technical background from the latest answer alone."
            ),
            handler=lambda context, call: retriever.search_technology(
                project_id=context.project_id,
                query=call.query,
                limit=call.args.get("limit", 5),
            ),
            requires_project=True,
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Technology, architecture topic, tool, failure mode, or project claim.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of technical evidence items to return.",
                        "minimum": 1,
                        "maximum": 8,
                        "default": 5,
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
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
