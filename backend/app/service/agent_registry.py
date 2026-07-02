from dataclasses import dataclass
from typing import Iterable

from app.service.prompt_manifest_validator import GovernanceCheckResult
from app.service.prompt_registry import AgentMetadata, PromptDefinition, PromptRegistry, prompt_registry


ALLOWED_AGENT_CATEGORIES = frozenset(
    {
        "analysis",
        "planning",
        "runtime",
        "runtime_judgement",
        "memory",
        "evaluation",
        "profile",
        "verification",
        "artifact_generation",
    }
)

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
    category: str | None = None
    responsibility: str | None = None
    owns: tuple[str, ...] = ()
    not_responsible_for: tuple[str, ...] = ()

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
            self._validate_definition(definition, errors, warnings)

        self._validate_orphan_metadata(definitions, errors)

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
            "categories": sorted({definition.category for definition in definitions if definition.category}),
            "allowed_categories": sorted(ALLOWED_AGENT_CATEGORIES),
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
        metadata_by_agent = {
            metadata.agent_name: metadata
            for metadata in self._all_agent_metadata()
        }
        return {
            agent_name: self._definition_from_group(agent_name, tuple(bindings), metadata_by_agent)
            for agent_name, bindings in grouped.items()
        }

    def _definition_from_group(
        self,
        agent_name: str,
        bindings: tuple[AgentPromptBinding, ...],
        metadata_by_agent: dict[str, AgentMetadata],
    ) -> AgentDefinition:
        metadata = self._metadata(metadata_by_agent, agent_name)
        return AgentDefinition(
            agent_name=agent_name,
            prompts=bindings,
            category=metadata.category,
            responsibility=metadata.responsibility,
            owns=metadata.owns,
            not_responsible_for=metadata.not_responsible_for,
        )

    def _metadata(
        self,
        metadata_by_agent: dict[str, AgentMetadata],
        agent_name: str,
    ) -> AgentMetadata:
        metadata = metadata_by_agent.get(agent_name)
        if metadata:
            return metadata
        return AgentMetadata(
            agent_name=agent_name,
            category="",
            responsibility="",
        )

    def _validate_definition(
        self,
        definition: AgentDefinition,
        errors: list[str],
        warnings: list[str],
    ) -> None:
        prefix = f"Agent '{definition.agent_name}'"
        if not definition.agent_name:
            errors.append("Agent definition missing agent_name")
        if not definition.prompts:
            errors.append(f"{prefix} has no prompt bindings")
        if not definition.category:
            errors.append(f"{prefix} missing category")
        elif definition.category not in ALLOWED_AGENT_CATEGORIES:
            errors.append(f"{prefix} has unknown category: {definition.category}")
        if not definition.responsibility:
            errors.append(f"{prefix} missing responsibility")
        if not definition.owns:
            warnings.append(f"{prefix} has empty owns boundary")
        if not definition.not_responsible_for:
            warnings.append(f"{prefix} has empty not_responsible_for boundary")

        duplicate_prompt_ids = self._duplicates(definition.prompt_ids)
        for prompt_id in duplicate_prompt_ids:
            errors.append(f"{prefix} has duplicate prompt binding: {prompt_id}")

        duplicate_tasks = self._duplicates(definition.tasks)
        for task in duplicate_tasks:
            errors.append(f"{prefix} has duplicate task binding: {task}")

        for task in definition.tasks:
            if task not in definition.owns:
                errors.append(f"{prefix} task is not declared in owns boundary: {task}")
        for owned_task in definition.owns:
            if owned_task not in definition.tasks:
                warnings.append(f"{prefix} owns boundary has no prompt task: {owned_task}")

        for binding in definition.prompts:
            binding_prefix = f"{prefix} prompt '{binding.prompt_id}'"
            self._require_value(binding_prefix, "prompt_id", binding.prompt_id, errors)
            self._require_value(binding_prefix, "prompt_version", binding.prompt_version, errors)
            self._require_value(binding_prefix, "task", binding.task, errors)
            self._require_value(binding_prefix, "input_schema", binding.input_schema, errors)
            self._require_value(binding_prefix, "output_schema", binding.output_schema, errors)

    def _validate_orphan_metadata(
        self,
        definitions: tuple[AgentDefinition, ...],
        errors: list[str],
    ) -> None:
        defined_agents = {definition.agent_name for definition in definitions}
        for metadata in self._all_agent_metadata():
            if metadata.agent_name not in defined_agents:
                errors.append(f"Agent metadata has no prompt owner: {metadata.agent_name}")

    def _all_agent_metadata(self) -> tuple[AgentMetadata, ...]:
        if not hasattr(self.prompts, "all_agent_metadata"):
            return ()
        return self.prompts.all_agent_metadata()

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


class AgentDefinitionValidator:
    def __init__(self, registry: AgentRegistry = agent_registry) -> None:
        self.registry = registry

    def validate_prompt_definition(
        self,
        definition: PromptDefinition,
    ) -> GovernanceCheckResult:
        errors: list[str] = []
        warnings: list[str] = []

        try:
            agent_definition = self.registry.get(definition.owner_agent)
        except KeyError:
            agent_definition = None
            errors.append(f"Agent definition not found: {definition.owner_agent}")

        binding = None
        if agent_definition:
            binding = self._binding_for_prompt(agent_definition, definition.prompt_id)
            if not binding:
                errors.append(
                    f"Agent '{definition.owner_agent}' does not bind prompt: {definition.prompt_id}"
                )

        if binding:
            self._validate_binding(definition, binding, errors)

        metadata = {
            "agent_name": definition.owner_agent,
            "prompt_id": definition.prompt_id,
            "task_name": definition.task,
            "prompt_version": definition.version,
            "input_schema": definition.input_schema,
            "output_schema": definition.output_schema,
        }
        return GovernanceCheckResult(
            ok=not errors,
            errors=tuple(errors),
            warnings=tuple(warnings),
            metadata=metadata,
        )

    def _binding_for_prompt(
        self,
        definition: AgentDefinition,
        prompt_id: str,
    ) -> AgentPromptBinding | None:
        for binding in definition.prompts:
            if binding.prompt_id == prompt_id:
                return binding
        return None

    def _validate_binding(
        self,
        definition: PromptDefinition,
        binding: AgentPromptBinding,
        errors: list[str],
    ) -> None:
        prefix = f"Agent '{definition.owner_agent}' prompt '{definition.prompt_id}'"
        if binding.prompt_version != definition.version:
            errors.append(
                f"{prefix} prompt_version mismatch: "
                f"definition={definition.version}, registry={binding.prompt_version}"
            )
        if binding.task != definition.task:
            errors.append(
                f"{prefix} task mismatch: definition={definition.task}, registry={binding.task}"
            )
        if binding.input_schema != definition.input_schema:
            errors.append(
                f"{prefix} input_schema mismatch: "
                f"definition={definition.input_schema}, registry={binding.input_schema}"
            )
        if binding.output_schema != definition.output_schema:
            errors.append(
                f"{prefix} output_schema mismatch: "
                f"definition={definition.output_schema}, registry={binding.output_schema}"
            )
        if binding.required_context != definition.required_context:
            errors.append(f"{prefix} required_context mismatch")
        if binding.optional_context != definition.optional_context:
            errors.append(f"{prefix} optional_context mismatch")
        if binding.required_evidence != definition.required_evidence:
            errors.append(f"{prefix} required_evidence mismatch")
