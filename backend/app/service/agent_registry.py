from dataclasses import dataclass
from typing import Iterable

from app.service.prompt_manifest_validator import GovernanceCheckResult
from app.service.prompt_registry import PromptDefinition, PromptRegistry, prompt_registry

# 表示Agent绑定的一个prompt/task
@dataclass(frozen=True)
class AgentPromptBinding:
    prompt_id: str
    prompt_version: str
    task: str
    input_schema: str
    output_schema: str
    required_context: tuple[str, ...] = ()
    optional_context: tuple[str, ...] = ()
    required_evidence: tuple[str, ...] = ()

# 表示一个完整的Agent定义，包括它绑定的所有prompt/task
@dataclass(frozen=True)
class AgentDefinition:
    agent_name: str
    prompts: tuple[AgentPromptBinding, ...]

    @property
    def prompt_ids(self) -> tuple[str, ...]:
        return tuple(binding.prompt_id for binding in self.prompts)

    @property
    def tasks(self) -> tuple[str, ...]:
        return tuple(binding.task for binding in self.prompts)

    @property
    def input_schemas(self) -> tuple[str, ...]:
        return self._unique(binding.input_schema for binding in self.prompts)

    @property
    def output_schemas(self) -> tuple[str, ...]:
        return self._unique(binding.output_schema for binding in self.prompts)

    @property
    def required_context(self) -> tuple[str, ...]:
        return self._unique(
            context_name
            for binding in self.prompts
            for context_name in binding.required_context
        )

    @property
    def optional_context(self) -> tuple[str, ...]:
        return self._unique(
            context_name
            for binding in self.prompts
            for context_name in binding.optional_context
        )

    @property
    def required_evidence(self) -> tuple[str, ...]:
        return self._unique(
            evidence_type
            for binding in self.prompts
            for evidence_type in binding.required_evidence
        )

    def _unique(self, values: Iterable[str]) -> tuple[str, ...]:
        seen = set()
        result = []
        for value in values:
            if value and value not in seen:
                seen.add(value)
                result.append(value)
        return tuple(result)

# 从PromptRegistry读取所有prompt，按照owner_agent分组
class AgentRegistry:
    def __init__(self, prompts: PromptRegistry = prompt_registry) -> None:
        self.prompts = prompts
        self._definitions = self._build_definitions(prompts.all())

    def get(self, agent_name: str) -> AgentDefinition:
        definition = self._definitions.get(agent_name)
        if not definition:
            raise KeyError(f"Agent definition not found: {agent_name}")
        return definition

    def all(self) -> tuple[AgentDefinition, ...]:
        return tuple(self._definitions[agent_name] for agent_name in sorted(self._definitions))

    def validate(self) -> GovernanceCheckResult:
        definitions = self.all()
        errors: list[str] = []
        warnings: list[str] = []

        if not definitions:
            errors.append("Agent registry has no agent definitions")

        for definition in definitions:
            self._validate_definition(definition, errors)

        multi_prompt_agents = [
            definition.agent_name
            for definition in definitions
            if len(definition.prompts) > 1
        ]
        metadata = {
            "agent_count": len(definitions),
            "agent_names": [definition.agent_name for definition in definitions],
            "prompt_count": sum(len(definition.prompts) for definition in definitions),
            "multi_prompt_agents": multi_prompt_agents,
        }
        return GovernanceCheckResult(
            ok=not errors,
            errors=tuple(errors),
            warnings=tuple(warnings),
            metadata=metadata,
        )

    def _build_definitions(
        self,
        prompt_definitions: tuple[PromptDefinition, ...],
    ) -> dict[str, AgentDefinition]:
        grouped: dict[str, list[AgentPromptBinding]] = {}
        for definition in prompt_definitions:
            grouped.setdefault(definition.owner_agent, []).append(
                AgentPromptBinding(
                    prompt_id=definition.prompt_id,
                    prompt_version=definition.version,
                    task=definition.task,
                    input_schema=definition.input_schema,
                    output_schema=definition.output_schema,
                    required_context=definition.required_context,
                    optional_context=definition.optional_context,
                    required_evidence=definition.required_evidence,
                )
            )
        return {
            agent_name: AgentDefinition(
                agent_name=agent_name,
                prompts=tuple(bindings),
            )
            for agent_name, bindings in grouped.items()
        }

    def _validate_definition(
        self,
        definition: AgentDefinition,
        errors: list[str],
    ) -> None:
        prefix = f"Agent '{definition.agent_name}'"
        if not definition.agent_name:
            errors.append("Agent definition missing agent_name")
        if not definition.prompts:
            errors.append(f"{prefix} has no prompt bindings")

        duplicate_prompt_ids = self._duplicates(definition.prompt_ids)
        for prompt_id in duplicate_prompt_ids:
            errors.append(f"{prefix} has duplicate prompt binding: {prompt_id}")

        duplicate_tasks = self._duplicates(definition.tasks)
        for task in duplicate_tasks:
            errors.append(f"{prefix} has duplicate task binding: {task}")

        for binding in definition.prompts:
            binding_prefix = f"{prefix} prompt '{binding.prompt_id}'"
            self._require_value(binding_prefix, "prompt_id", binding.prompt_id, errors)
            self._require_value(binding_prefix, "prompt_version", binding.prompt_version, errors)
            self._require_value(binding_prefix, "task", binding.task, errors)
            self._require_value(binding_prefix, "input_schema", binding.input_schema, errors)
            self._require_value(binding_prefix, "output_schema", binding.output_schema, errors)

    def _require_value(
        self,
        prefix: str,
        field_name: str,
        value: str | None,
        errors: list[str],
    ) -> None:
        if not value:
            errors.append(f"{prefix} missing {field_name}")

    def _duplicates(self, values: tuple[str, ...]) -> tuple[str, ...]:
        seen = set()
        duplicates = []
        for value in values:
            if value in seen:
                duplicates.append(value)
            seen.add(value)
        return tuple(sorted(set(duplicates)))


agent_registry = AgentRegistry()
