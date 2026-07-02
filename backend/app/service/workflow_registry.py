from dataclasses import dataclass

from app.service.agent_registry import AgentRegistry, agent_registry
from app.service.prompt_manifest_validator import GovernanceCheckResult
from app.service.prompt_registry import (
    PromptRegistry,
    WorkflowMetadata,
    WorkflowStepMetadata,
    prompt_registry,
)


@dataclass(frozen=True)
class WorkflowStepDefinition:
    step_id: str
    agent_name: str
    prompt_id: str
    task: str
    required: bool = True
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkflowDefinition:
    workflow_id: str
    name: str
    description: str
    steps: tuple[WorkflowStepDefinition, ...]

    @property
    def step_ids(self) -> tuple[str, ...]:
        return tuple(step.step_id for step in self.steps)

    @property
    def agent_names(self) -> tuple[str, ...]:
        return self._unique(step.agent_name for step in self.steps)

    @property
    def prompt_ids(self) -> tuple[str, ...]:
        return self._unique(step.prompt_id for step in self.steps)

    @property
    def tasks(self) -> tuple[str, ...]:
        return self._unique(step.task for step in self.steps)

    def _unique(self, values) -> tuple[str, ...]:
        seen = set()
        result = []
        for value in values:
            if value and value not in seen:
                seen.add(value)
                result.append(value)
        return tuple(result)


class WorkflowRegistry:
    def __init__(
        self,
        prompts: PromptRegistry = prompt_registry,
        agents: AgentRegistry = agent_registry,
    ) -> None:
        self.prompts = prompts
        self.agents = agents
        self._definitions = {
            workflow.workflow_id: self._definition_from_metadata(workflow)
            for workflow in self._all_workflow_metadata()
        }

    def get(self, workflow_id: str) -> WorkflowDefinition:
        definition = self._definitions.get(workflow_id)
        if not definition:
            raise KeyError(f"Workflow definition not found: {workflow_id}")
        return definition

    def all(self) -> tuple[WorkflowDefinition, ...]:
        return tuple(self._definitions[workflow_id] for workflow_id in sorted(self._definitions))

    def validate(self) -> GovernanceCheckResult:
        definitions = self.all()
        errors: list[str] = []
        warnings: list[str] = []

        if not definitions:
            errors.append("Workflow registry has no workflow definitions")

        for definition in definitions:
            self._validate_definition(definition, errors, warnings)

        metadata = {
            "workflow_count": len(definitions),
            "workflow_ids": [definition.workflow_id for definition in definitions],
            "step_count": sum(len(definition.steps) for definition in definitions),
        }
        return GovernanceCheckResult(
            ok=not errors,
            errors=tuple(errors),
            warnings=tuple(warnings),
            metadata=metadata,
        )

    def _definition_from_metadata(self, metadata: WorkflowMetadata) -> WorkflowDefinition:
        return WorkflowDefinition(
            workflow_id=metadata.workflow_id,
            name=metadata.name,
            description=metadata.description,
            steps=tuple(
                self._step_definition_from_metadata(step)
                for step in metadata.steps
            ),
        )

    def _step_definition_from_metadata(
        self,
        metadata: WorkflowStepMetadata,
    ) -> WorkflowStepDefinition:
        return WorkflowStepDefinition(
            step_id=metadata.step_id,
            agent_name=metadata.agent_name,
            prompt_id=metadata.prompt_id,
            task=metadata.task,
            required=metadata.required,
            depends_on=metadata.depends_on,
        )

    def _validate_definition(
        self,
        definition: WorkflowDefinition,
        errors: list[str],
        warnings: list[str],
    ) -> None:
        prefix = f"Workflow '{definition.workflow_id}'"
        self._require_value(prefix, "workflow_id", definition.workflow_id, errors)
        self._require_value(prefix, "name", definition.name, errors)
        self._require_value(prefix, "description", definition.description, errors)
        if not definition.steps:
            errors.append(f"{prefix} has no steps")

        duplicate_step_ids = self._duplicates(definition.step_ids)
        for step_id in duplicate_step_ids:
            errors.append(f"{prefix} has duplicate step_id: {step_id}")

        step_ids = set(definition.step_ids)
        for step in definition.steps:
            self._validate_step(definition, step, step_ids, errors)

        for cycle in self._cycles(definition):
            errors.append(f"{prefix} has cyclic dependency: {' -> '.join(cycle)}")

        if not any(step.required for step in definition.steps):
            warnings.append(f"{prefix} has no required steps")

    def _validate_step(
        self,
        definition: WorkflowDefinition,
        step: WorkflowStepDefinition,
        step_ids: set[str],
        errors: list[str],
    ) -> None:
        prefix = f"Workflow '{definition.workflow_id}' step '{step.step_id}'"
        self._require_value(prefix, "step_id", step.step_id, errors)
        self._require_value(prefix, "agent_name", step.agent_name, errors)
        self._require_value(prefix, "prompt_id", step.prompt_id, errors)
        self._require_value(prefix, "task", step.task, errors)

        for dependency in step.depends_on:
            if dependency not in step_ids:
                errors.append(f"{prefix} depends on unknown step: {dependency}")
            if dependency == step.step_id:
                errors.append(f"{prefix} depends on itself")

        try:
            agent = self.agents.get(step.agent_name)
        except KeyError:
            agent = None
            errors.append(f"{prefix} references unknown agent: {step.agent_name}")

        try:
            prompt = self.prompts.get(step.prompt_id)
        except KeyError:
            prompt = None
            errors.append(f"{prefix} references unknown prompt: {step.prompt_id}")

        if agent and step.prompt_id not in agent.prompt_ids:
            errors.append(f"{prefix} prompt is not bound to agent: {step.prompt_id}")
        if agent and step.task not in agent.tasks:
            errors.append(f"{prefix} task is not owned by agent: {step.task}")
        if prompt and prompt.owner_agent != step.agent_name:
            errors.append(
                f"{prefix} agent mismatch: workflow={step.agent_name}, prompt={prompt.owner_agent}"
            )
        if prompt and prompt.task != step.task:
            errors.append(f"{prefix} task mismatch: workflow={step.task}, prompt={prompt.task}")

    def _cycles(self, definition: WorkflowDefinition) -> tuple[tuple[str, ...], ...]:
        graph = {step.step_id: tuple(step.depends_on) for step in definition.steps}
        cycles: list[tuple[str, ...]] = []
        visited: set[str] = set()
        active: set[str] = set()

        def visit(step_id: str, path: list[str]) -> None:
            if step_id in active:
                start = path.index(step_id)
                cycles.append(tuple(path[start:] + [step_id]))
                return
            if step_id in visited:
                return
            active.add(step_id)
            path.append(step_id)
            for dependency in graph.get(step_id, ()):
                if dependency in graph:
                    visit(dependency, path)
            path.pop()
            active.remove(step_id)
            visited.add(step_id)

        for step_id in graph:
            visit(step_id, [])
        return tuple(cycles)

    def _all_workflow_metadata(self) -> tuple[WorkflowMetadata, ...]:
        if not hasattr(self.prompts, "all_workflow_metadata"):
            return ()
        return self.prompts.all_workflow_metadata()

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


workflow_registry = WorkflowRegistry()
