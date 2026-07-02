import unittest
from types import SimpleNamespace

from service.support import configure_backend_imports

configure_backend_imports()

from app.service.prompt_manifest_validator import GovernanceCheckResult, PromptManifestValidator
from app.service.prompt_registry import AgentMetadata, PromptDefinition, PromptRegistry
from app.service.evidence_contract import ALLOWED_EVIDENCE_TYPES


def prompt_definition(**overrides) -> PromptDefinition:
    values = {
        "prompt_id": "test_prompt",
        "prompt_file": "interviewer.txt",
        "version": "3.0.0",
        "owner_agent": "TestAgent",
        "task": "test_task",
        "input_schema": "TestInput.v1",
        "output_schema": "TestOutput.v1",
        "required_context": ("RoleName",),
        "optional_context": (),
        "required_evidence": ("interview_answer",),
    }
    values.update(overrides)
    return PromptDefinition(**values)


def registry_with(*definitions: PromptDefinition):
    return SimpleNamespace(
        manifest_path="memory://manifest.json",
        all=lambda: tuple(definitions),
        all_agent_metadata=lambda: (
            AgentMetadata(
                agent_name="TestAgent",
                category="analysis",
                responsibility="Test agent responsibility.",
                owns=("test_task",),
                not_responsible_for=("runtime execution",),
            ),
        ),
    )


def registry_with_metadata(definitions: tuple[PromptDefinition, ...], metadata: tuple[AgentMetadata, ...]):
    return SimpleNamespace(
        manifest_path="memory://manifest.json",
        all=lambda: tuple(definitions),
        all_agent_metadata=lambda: tuple(metadata),
    )


class PromptManifestValidatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = PromptManifestValidator()

    def test_current_manifest_is_healthy(self):
        result = self.validator.validate(PromptRegistry())

        self.assertTrue(result.ok)
        self.assertEqual(result.errors, ())
        self.assertEqual(result.warnings, ())
        self.assertGreaterEqual(result.metadata["prompt_count"], 1)
        self.assertIn("resume_rewrite", result.metadata["prompt_ids"])
        self.assertIn("ResumeRewriteAgent", result.metadata["owner_agents"])
        self.assertIn("interview_answer", result.metadata["allowed_evidence_types"])
        self.assertIn("artifact_generation", result.metadata["agent_categories"])
        self.assertIn("analysis", result.metadata["allowed_agent_categories"])
        self.assertEqual(result.metadata["allowed_evidence_types"], sorted(ALLOWED_EVIDENCE_TYPES))

    def test_registry_validate_uses_manifest_validator(self):
        result = PromptRegistry().validate()

        self.assertTrue(result.ok)
        self.assertIn("prompt_count", result.metadata)

    def test_result_can_be_serialized_to_dict(self):
        result = GovernanceCheckResult(
            ok=False,
            errors=("broken",),
            warnings=("risky",),
            metadata={"prompt_count": 1},
        )

        self.assertEqual(
            result.to_dict(),
            {
                "ok": False,
                "errors": ["broken"],
                "warnings": ["risky"],
                "metadata": {"prompt_count": 1},
            },
        )

    def test_unknown_required_context_and_evidence_are_errors(self):
        result = self.validator.validate(
            registry_with(
                prompt_definition(
                    required_context=("UnknownContext",),
                    required_evidence=("unknown_evidence",),
                )
            )
        )

        self.assertFalse(result.ok)
        self.assertIn(
            "Prompt 'test_prompt' has unknown required_context: UnknownContext",
            result.errors,
        )
        self.assertIn(
            "Prompt 'test_prompt' has unknown required_evidence: unknown_evidence",
            result.errors,
        )

    def test_unknown_optional_context_is_warning(self):
        result = self.validator.validate(
            registry_with(
                prompt_definition(optional_context=("UnknownOptionalContext",))
            )
        )

        self.assertTrue(result.ok)
        self.assertIn(
            "Prompt 'test_prompt' has unknown optional_context: UnknownOptionalContext",
            result.warnings,
        )

    def test_duplicate_context_and_evidence_are_reported(self):
        result = self.validator.validate(
            registry_with(
                prompt_definition(
                    required_context=("RoleName", "RoleName"),
                    optional_context=("CandidateProfile", "CandidateProfile"),
                    required_evidence=("interview_answer", "interview_answer"),
                )
            )
        )

        self.assertFalse(result.ok)
        self.assertIn(
            "Prompt 'test_prompt' has duplicate required_context: RoleName",
            result.errors,
        )
        self.assertIn(
            "Prompt 'test_prompt' has duplicate optional_context: CandidateProfile",
            result.warnings,
        )
        self.assertIn(
            "Prompt 'test_prompt' has duplicate required_evidence: interview_answer",
            result.errors,
        )

    def test_invalid_naming_and_missing_prompt_file_are_errors(self):
        result = self.validator.validate(
            registry_with(
                prompt_definition(
                    prompt_id="BadPrompt",
                    prompt_file="missing_prompt.txt",
                    version="v3",
                    task="BadTask",
                    input_schema="bad_input",
                    output_schema="bad_output",
                )
            )
        )

        self.assertFalse(result.ok)
        self.assertIn("Prompt 'BadPrompt' has invalid prompt_id naming: BadPrompt", result.errors)
        self.assertIn("Prompt 'BadPrompt' has invalid task naming: BadTask", result.errors)
        self.assertIn("Prompt 'BadPrompt' has invalid semantic version: v3", result.errors)
        self.assertIn("Prompt 'BadPrompt' has invalid input_schema naming: bad_input", result.errors)
        self.assertIn("Prompt 'BadPrompt' has invalid output_schema naming: bad_output", result.errors)
        self.assertIn("Prompt 'BadPrompt' references missing prompt_file: missing_prompt.txt", result.errors)

    def test_duplicate_prompt_ids_are_errors(self):
        result = self.validator.validate(
            registry_with(
                prompt_definition(prompt_id="same_prompt"),
                prompt_definition(prompt_id="same_prompt"),
            )
        )

        self.assertFalse(result.ok)
        self.assertIn("Duplicate prompt_id: same_prompt", result.errors)

    def test_missing_agent_metadata_is_error(self):
        result = self.validator.validate(
            registry_with_metadata(
                definitions=(prompt_definition(),),
                metadata=(),
            )
        )

        self.assertFalse(result.ok)
        self.assertIn("Agent 'TestAgent' missing metadata definition", result.errors)

    def test_unknown_agent_category_and_missing_boundaries_are_reported(self):
        result = self.validator.validate(
            registry_with_metadata(
                definitions=(prompt_definition(),),
                metadata=(
                    AgentMetadata(
                        agent_name="TestAgent",
                        category="unknown",
                        responsibility="Test agent responsibility.",
                    ),
                ),
            )
        )

        self.assertFalse(result.ok)
        self.assertIn("Agent 'TestAgent' has unknown category: unknown", result.errors)
        self.assertIn("Agent 'TestAgent' task is not declared in owns boundary: test_task", result.errors)
        self.assertIn("Agent 'TestAgent' has empty owns boundary", result.warnings)
        self.assertIn("Agent 'TestAgent' has empty not_responsible_for boundary", result.warnings)

    def test_orphan_agent_metadata_is_error(self):
        result = self.validator.validate(
            registry_with_metadata(
                definitions=(prompt_definition(),),
                metadata=(
                    AgentMetadata(
                        agent_name="TestAgent",
                        category="analysis",
                        responsibility="Test agent responsibility.",
                        owns=("test_task",),
                        not_responsible_for=("runtime execution",),
                    ),
                    AgentMetadata(
                        agent_name="OrphanAgent",
                        category="analysis",
                        responsibility="Orphan metadata.",
                        owns=("orphan_task",),
                        not_responsible_for=("runtime execution",),
                    ),
                ),
            )
        )

        self.assertFalse(result.ok)
        self.assertIn("Agent metadata has no prompt owner: OrphanAgent", result.errors)


if __name__ == "__main__":
    unittest.main()
