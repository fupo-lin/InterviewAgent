import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.service.evidence_contract import ALLOWED_EVIDENCE_TYPES
from app.service.prompt_contract import PromptContractValidator
from app.service.prompt_registry import PROMPT_DIR, PromptDefinition


@dataclass(frozen=True)
class GovernanceCheckResult:
    ok: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "metadata": self.metadata,
        }


class PromptManifestValidator:
    PROMPT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
    TASK_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
    VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
    SCHEMA_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9]*\.v\d+$")

    def __init__(
        self,
        prompt_dir: Path = PROMPT_DIR,
        allowed_evidence_types: frozenset[str] = ALLOWED_EVIDENCE_TYPES,
    ) -> None:
        self.prompt_dir = prompt_dir
        self.allowed_evidence_types = allowed_evidence_types
        self.known_context_names = frozenset(PromptContractValidator.CONTEXT_ALIASES)

    def validate(self, registry) -> GovernanceCheckResult:
        definitions = registry.all()
        errors: list[str] = []
        warnings: list[str] = []

        self._validate_unique_prompt_ids(definitions, errors)
        for definition in definitions:
            self._validate_definition(definition, errors, warnings)

        metadata = {
            "manifest_path": str(getattr(registry, "manifest_path", "")),
            "prompt_count": len(definitions),
            "prompt_ids": [definition.prompt_id for definition in definitions],
            "owner_agents": sorted({definition.owner_agent for definition in definitions}),
            "allowed_evidence_types": sorted(self.allowed_evidence_types),
        }
        return GovernanceCheckResult(
            ok=not errors,
            errors=tuple(errors),
            warnings=tuple(warnings),
            metadata=metadata,
        )

    def _validate_unique_prompt_ids(
        self,
        definitions: tuple[PromptDefinition, ...],
        errors: list[str],
    ) -> None:
        seen = set()
        duplicates = []
        for definition in definitions:
            if definition.prompt_id in seen:
                duplicates.append(definition.prompt_id)
            seen.add(definition.prompt_id)
        for prompt_id in sorted(set(duplicates)):
            errors.append(f"Duplicate prompt_id: {prompt_id}")

    def _validate_definition(
        self,
        definition: PromptDefinition,
        errors: list[str],
        warnings: list[str],
    ) -> None:
        prefix = f"Prompt '{definition.prompt_id}'"
        self._require_value(prefix, "prompt_id", definition.prompt_id, errors)
        self._require_value(prefix, "prompt_file", definition.prompt_file, errors)
        self._require_value(prefix, "version", definition.version, errors)
        self._require_value(prefix, "owner_agent", definition.owner_agent, errors)
        self._require_value(prefix, "task", definition.task, errors)
        self._require_value(prefix, "input_schema", definition.input_schema, errors)
        self._require_value(prefix, "output_schema", definition.output_schema, errors)

        if definition.prompt_id and not self.PROMPT_ID_PATTERN.match(definition.prompt_id):
            errors.append(f"{prefix} has invalid prompt_id naming: {definition.prompt_id}")
        if definition.task and not self.TASK_PATTERN.match(definition.task):
            errors.append(f"{prefix} has invalid task naming: {definition.task}")
        if definition.version and not self.VERSION_PATTERN.match(definition.version):
            errors.append(f"{prefix} has invalid semantic version: {definition.version}")
        if definition.input_schema and not self.SCHEMA_PATTERN.match(definition.input_schema):
            errors.append(f"{prefix} has invalid input_schema naming: {definition.input_schema}")
        if definition.output_schema and not self.SCHEMA_PATTERN.match(definition.output_schema):
            errors.append(f"{prefix} has invalid output_schema naming: {definition.output_schema}")
        if definition.prompt_file and not (self.prompt_dir / definition.prompt_file).exists():
            errors.append(f"{prefix} references missing prompt_file: {definition.prompt_file}")

        self._validate_contexts(prefix, "required_context", definition.required_context, errors)
        self._validate_contexts(prefix, "optional_context", definition.optional_context, warnings)
        self._validate_evidence(prefix, definition.required_evidence, errors)

    def _require_value(
        self,
        prefix: str,
        field_name: str,
        value: str | None,
        errors: list[str],
    ) -> None:
        if not value:
            errors.append(f"{prefix} missing {field_name}")

    def _validate_contexts(
        self,
        prefix: str,
        field_name: str,
        contexts: tuple[str, ...],
        messages: list[str],
    ) -> None:
        duplicates = self._duplicates(contexts)
        for context_name in duplicates:
            messages.append(f"{prefix} has duplicate {field_name}: {context_name}")
        for context_name in contexts:
            if context_name not in self.known_context_names:
                messages.append(f"{prefix} has unknown {field_name}: {context_name}")

    def _validate_evidence(
        self,
        prefix: str,
        required_evidence: tuple[str, ...],
        errors: list[str],
    ) -> None:
        duplicates = self._duplicates(required_evidence)
        for evidence_type in duplicates:
            errors.append(f"{prefix} has duplicate required_evidence: {evidence_type}")
        for evidence_type in required_evidence:
            if evidence_type not in self.allowed_evidence_types:
                errors.append(f"{prefix} has unknown required_evidence: {evidence_type}")

    def _duplicates(self, values: tuple[str, ...]) -> tuple[str, ...]:
        seen = set()
        duplicates = []
        for value in values:
            if value in seen:
                duplicates.append(value)
            seen.add(value)
        return tuple(sorted(set(duplicates)))
