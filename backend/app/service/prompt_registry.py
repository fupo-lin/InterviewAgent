import json
from dataclasses import dataclass, field
from pathlib import Path


PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"
MANIFEST_PATH = PROMPT_DIR / "manifest.json"


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
        self._definitions = {
            item.prompt_id: item
            for item in self._load_manifest(manifest_path)
        }

    def get(self, prompt_id: str) -> PromptDefinition:
        definition = self._definitions.get(prompt_id)
        if not definition:
            raise KeyError(f"Prompt definition not found: {prompt_id}")
        return definition

    def prompt_file(self, prompt_id: str) -> str:
        return self.get(prompt_id).prompt_file

    def _load_manifest(self, manifest_path: Path) -> list[PromptDefinition]:
        if not manifest_path.exists():
            raise FileNotFoundError(f"Prompt manifest not found: {manifest_path}")

        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        prompts = data.get("prompts")
        if not isinstance(prompts, list):
            raise ValueError("Prompt manifest must contain a 'prompts' list")

        definitions = [self._definition_from_item(item) for item in prompts]
        prompt_ids = [item.prompt_id for item in definitions]
        if len(prompt_ids) != len(set(prompt_ids)):
            raise ValueError("Prompt manifest contains duplicate prompt_id values")
        return definitions

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


prompt_registry = PromptRegistry()
