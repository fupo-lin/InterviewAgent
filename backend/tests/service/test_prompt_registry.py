import json
import tempfile
import unittest
from pathlib import Path

from service.support import configure_backend_imports

configure_backend_imports()

from app.service.prompt_registry import PROMPT_DIR, PromptRegistry


def valid_prompt_item(prompt_id: str = "test_prompt") -> dict:
    return {
        "prompt_id": prompt_id,
        "prompt_file": "interviewer.txt",
        "version": "3.0.0",
        "owner_agent": "TestAgent",
        "task": "test_task",
        "input_schema": "TestInput.v1",
        "output_schema": "TestOutput.v1",
        "required_context": ["RoleName"],
        "optional_context": [],
        "required_evidence": [],
    }


def valid_agent_item() -> dict:
    return {
        "agent_name": "TestAgent",
        "category": "analysis",
        "responsibility": "Validate prompt registry loading in tests.",
        "owns": ["test_task"],
        "not_responsible_for": ["runtime execution"],
    }


def write_manifest(temp_dir: tempfile.TemporaryDirectory, content: dict) -> Path:
    manifest_path = Path(temp_dir.name) / "manifest.json"
    manifest_path.write_text(json.dumps(content), encoding="utf-8")
    return manifest_path


class PromptRegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dirs: list[tempfile.TemporaryDirectory] = []

    def tearDown(self) -> None:
        for temp_dir in self.temp_dirs:
            temp_dir.cleanup()

    def write_manifest(self, content: dict) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.temp_dirs.append(temp_dir)
        return write_manifest(temp_dir, content)

    def test_current_manifest_loads_core_prompt_contracts(self):
        registry = PromptRegistry()

        resume_rewrite = registry.get("resume_rewrite")
        metadata = registry.agent_metadata("ResumeRewriteAgent")

        self.assertEqual(resume_rewrite.prompt_file, "resume_rewrite.txt")
        self.assertEqual(resume_rewrite.version, "3.0.0")
        self.assertEqual(resume_rewrite.owner_agent, "ResumeRewriteAgent")
        self.assertEqual(resume_rewrite.task, "resume_rewrite")
        self.assertEqual(resume_rewrite.input_schema, "ResumeRewriteInput.v1")
        self.assertEqual(resume_rewrite.output_schema, "ResumeRewriteResult.v1")
        self.assertEqual(resume_rewrite.required_context, ("ResumeDocument", "ResumeProfile"))
        self.assertEqual(resume_rewrite.required_evidence, ("resume_claim", "authenticity_check"))
        self.assertIsNotNone(metadata)
        self.assertEqual(metadata.category, "artifact_generation")
        self.assertEqual(metadata.owns, ("resume_rewrite",))
        self.assertEqual(registry.prompt_file("followup"), "followup.txt")

    def test_current_manifest_prompt_files_exist(self):
        registry = PromptRegistry()

        definitions = registry.all()
        self.assertTrue(definitions)
        for definition in definitions:
            with self.subTest(prompt_id=definition.prompt_id):
                self.assertTrue((PROMPT_DIR / definition.prompt_file).exists())
                self.assertTrue(definition.version)
                self.assertTrue(definition.owner_agent)
                self.assertTrue(definition.task)
                self.assertTrue(definition.input_schema)
                self.assertTrue(definition.output_schema)
                self.assertIsInstance(definition.required_context, tuple)
                self.assertIsInstance(definition.optional_context, tuple)
                self.assertIsInstance(definition.required_evidence, tuple)

    def test_current_manifest_agent_metadata_exists_for_prompt_owners(self):
        registry = PromptRegistry()

        owner_agents = {definition.owner_agent for definition in registry.all()}
        metadata_agents = {metadata.agent_name for metadata in registry.all_agent_metadata()}

        self.assertTrue(owner_agents)
        self.assertEqual(owner_agents, metadata_agents)

    def test_manifest_must_contain_prompt_list(self):
        manifest_path = self.write_manifest({"prompts": {}})

        with self.assertRaisesRegex(ValueError, "prompts"):
            PromptRegistry(manifest_path=manifest_path)

    def test_manifest_rejects_missing_required_fields(self):
        manifest_path = self.write_manifest(
            {
                "prompts": [
                    {
                        "prompt_id": "broken_prompt",
                        "prompt_file": "interviewer.txt",
                    }
                ]
            }
        )

        with self.assertRaisesRegex(ValueError, "missing required fields"):
            PromptRegistry(manifest_path=manifest_path)

    def test_manifest_rejects_duplicate_prompt_ids(self):
        item = valid_prompt_item(prompt_id="duplicated_prompt")
        manifest_path = self.write_manifest({"prompts": [item, dict(item)]})

        with self.assertRaisesRegex(ValueError, "duplicate prompt_id"):
            PromptRegistry(manifest_path=manifest_path)

    def test_manifest_rejects_duplicate_agent_names(self):
        item = valid_prompt_item()
        agent = valid_agent_item()
        manifest_path = self.write_manifest({"agents": [agent, dict(agent)], "prompts": [item]})

        with self.assertRaisesRegex(ValueError, "duplicate agent_name"):
            PromptRegistry(manifest_path=manifest_path)

    def test_manifest_rejects_invalid_agents_section_shape(self):
        item = valid_prompt_item()
        manifest_path = self.write_manifest({"agents": {}, "prompts": [item]})

        with self.assertRaisesRegex(ValueError, "agents"):
            PromptRegistry(manifest_path=manifest_path)

    def test_manifest_rejects_missing_agent_metadata_required_fields(self):
        item = valid_prompt_item()
        manifest_path = self.write_manifest(
            {
                "agents": [{"agent_name": "TestAgent"}],
                "prompts": [item],
            }
        )

        with self.assertRaisesRegex(ValueError, "Agent metadata missing required fields"):
            PromptRegistry(manifest_path=manifest_path)

    def test_manifest_rejects_missing_prompt_file(self):
        item = valid_prompt_item()
        item["prompt_file"] = "missing_prompt_file.txt"
        manifest_path = self.write_manifest({"prompts": [item]})

        with self.assertRaisesRegex(FileNotFoundError, "Prompt file not found"):
            PromptRegistry(manifest_path=manifest_path)


if __name__ == "__main__":
    unittest.main()
