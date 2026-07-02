import json
from dataclasses import dataclass, field
from pathlib import Path


PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"
MANIFEST_PATH = PROMPT_DIR / "manifest.json"


@dataclass(frozen=True)
class AgentMetadata:
    agent_name: str
    category: str
    responsibility: str
    owns: tuple[str, ...] = field(default_factory=tuple)
    not_responsible_for: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class WorkflowStepMetadata:
    step_id: str
    agent_name: str
    prompt_id: str
    task: str
    required: bool = True
    depends_on: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class WorkflowMetadata:
    workflow_id: str
    name: str
    description: str
    steps: tuple[WorkflowStepMetadata, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PromptDefinition:
    prompt_id: str
    prompt_file: str
    version: str
    owner_agent: str
    task: str
    input_schema: str
    output_schema: str
    required_context: tuple[str, ...] = field(default_factory=tuple)
    optional_context: tuple[str, ...] = field(default_factory=tuple)
    required_evidence: tuple[str, ...] = field(default_factory=tuple)


class PromptRegistry:
    def __init__(self, manifest_path: Path = MANIFEST_PATH) -> None:
        self.manifest_path = manifest_path
        manifest = self._load_manifest(manifest_path)
        self._definitions = {
            item.prompt_id: item
            for item in manifest["prompts"]
        }
        self._agent_metadata = {
            item.agent_name: item
            for item in manifest["agents"]
        }
        self._workflow_metadata = {
            item.workflow_id: item
            for item in manifest["workflows"]
        }

    def get(self, prompt_id: str) -> PromptDefinition:
        definition = self._definitions.get(prompt_id)
        if not definition:
            raise KeyError(f"Prompt definition not found: {prompt_id}")
        return definition

    def prompt_file(self, prompt_id: str) -> str:
        return self.get(prompt_id).prompt_file

    def all(self) -> tuple[PromptDefinition, ...]:
        return tuple(self._definitions.values())

    def agent_metadata(self, agent_name: str) -> AgentMetadata | None:
        return self._agent_metadata.get(agent_name)

    def all_agent_metadata(self) -> tuple[AgentMetadata, ...]:
        return tuple(self._agent_metadata.values())

    def workflow_metadata(self, workflow_id: str) -> WorkflowMetadata | None:
        return self._workflow_metadata.get(workflow_id)

    def all_workflow_metadata(self) -> tuple[WorkflowMetadata, ...]:
        return tuple(self._workflow_metadata.values())

    def validate(self):
        from app.service.prompt_manifest_validator import PromptManifestValidator

        return PromptManifestValidator().validate(self)

    def _load_manifest(self, manifest_path: Path) -> dict:
        if not manifest_path.exists():
            raise FileNotFoundError(f"Prompt manifest not found: {manifest_path}")

        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        prompts = data.get("prompts")
        if not isinstance(prompts, list):
            raise ValueError("Prompt manifest must contain a 'prompts' list")

        prompt_definitions = [self._definition_from_item(item) for item in prompts]
        prompt_ids = [item.prompt_id for item in prompt_definitions]
        if len(prompt_ids) != len(set(prompt_ids)):
            raise ValueError("Prompt manifest contains duplicate prompt_id values")

        agent_items = data.get("agents", [])
        if not isinstance(agent_items, list):
            raise ValueError("Prompt manifest 'agents' must be a list when provided")
        agent_metadata = [self._agent_metadata_from_item(item) for item in agent_items]
        agent_names = [item.agent_name for item in agent_metadata]
        if len(agent_names) != len(set(agent_names)):
            raise ValueError("Prompt manifest contains duplicate agent_name values")

        workflow_items = data.get("workflows", [])
        if not isinstance(workflow_items, list):
            raise ValueError("Prompt manifest 'workflows' must be a list when provided")
        workflow_metadata = [self._workflow_metadata_from_item(item) for item in workflow_items]
        workflow_ids = [item.workflow_id for item in workflow_metadata]
        if len(workflow_ids) != len(set(workflow_ids)):
            raise ValueError("Prompt manifest contains duplicate workflow_id values")

        return {
            "prompts": prompt_definitions,
            "agents": agent_metadata,
            "workflows": workflow_metadata,
        }

    def _definition_from_item(self, item: dict) -> PromptDefinition:
        required_fields = (
            "prompt_id",
            "prompt_file",
            "version",
            "owner_agent",
            "task",
            "input_schema",
            "output_schema",
        )
        missing_fields = [field_name for field_name in required_fields if not item.get(field_name)]
        if missing_fields:
            raise ValueError(f"Prompt definition missing required fields: {missing_fields}")

        prompt_file = item["prompt_file"]
        if not (PROMPT_DIR / prompt_file).exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_file}")

        return PromptDefinition(
            prompt_id=item["prompt_id"],
            prompt_file=prompt_file,
            version=item["version"],
            owner_agent=item["owner_agent"],
            task=item["task"],
            input_schema=item["input_schema"],
            output_schema=item["output_schema"],
            required_context=tuple(item.get("required_context") or ()),
            optional_context=tuple(item.get("optional_context") or ()),
            required_evidence=tuple(item.get("required_evidence") or ()),
        )

    def _agent_metadata_from_item(self, item: dict) -> AgentMetadata:
        required_fields = (
            "agent_name",
            "category",
            "responsibility",
        )
        missing_fields = [field_name for field_name in required_fields if not item.get(field_name)]
        if missing_fields:
            raise ValueError(f"Agent metadata missing required fields: {missing_fields}")

        return AgentMetadata(
            agent_name=item["agent_name"],
            category=item["category"],
            responsibility=item["responsibility"],
            owns=tuple(item.get("owns") or ()),
            not_responsible_for=tuple(item.get("not_responsible_for") or ()),
        )

    def _workflow_metadata_from_item(self, item: dict) -> WorkflowMetadata:
        required_fields = (
            "workflow_id",
            "name",
            "description",
            "steps",
        )
        missing_fields = [field_name for field_name in required_fields if not item.get(field_name)]
        if missing_fields:
            raise ValueError(f"Workflow metadata missing required fields: {missing_fields}")

        steps = item["steps"]
        if not isinstance(steps, list):
            raise ValueError("Workflow metadata 'steps' must be a list")

        return WorkflowMetadata(
            workflow_id=item["workflow_id"],
            name=item["name"],
            description=item["description"],
            steps=tuple(self._workflow_step_from_item(step) for step in steps),
        )

    def _workflow_step_from_item(self, item: dict) -> WorkflowStepMetadata:
        required_fields = (
            "step_id",
            "agent_name",
            "prompt_id",
            "task",
        )
        missing_fields = [field_name for field_name in required_fields if not item.get(field_name)]
        if missing_fields:
            raise ValueError(f"Workflow step metadata missing required fields: {missing_fields}")

        return WorkflowStepMetadata(
            step_id=item["step_id"],
            agent_name=item["agent_name"],
            prompt_id=item["prompt_id"],
            task=item["task"],
            required=bool(item.get("required", True)),
            depends_on=tuple(item.get("depends_on") or ()),
        )


prompt_registry = PromptRegistry()
