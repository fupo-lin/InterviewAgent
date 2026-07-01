import unittest
from types import SimpleNamespace

from service.support import configure_backend_imports

configure_backend_imports()

from app.service.agent_registry import AgentRegistry
from app.service.prompt_registry import PromptDefinition, PromptRegistry


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


def prompt_registry_with(*definitions: PromptDefinition):
    return SimpleNamespace(all=lambda: tuple(definitions))


class AgentRegistryTest(unittest.TestCase):
    def test_current_manifest_builds_agent_definitions(self):
        registry = AgentRegistry(PromptRegistry())

        definition = registry.get("ResumeRewriteAgent")

        self.assertEqual(definition.agent_name, "ResumeRewriteAgent")
        self.assertEqual(definition.prompt_ids, ("resume_rewrite",))
        self.assertEqual(definition.tasks, ("resume_rewrite",))
        self.assertEqual(definition.input_schemas, ("ResumeRewriteInput.v1",))
        self.assertEqual(definition.output_schemas, ("ResumeRewriteResult.v1",))
        self.assertEqual(definition.required_context, ("ResumeDocument", "ResumeProfile"))
        self.assertEqual(
            definition.required_evidence,
            ("resume_claim", "authenticity_check"),
        )

    def test_groups_multiple_prompts_under_same_agent(self):
        registry = AgentRegistry(PromptRegistry())

        interview_executor = registry.get("InterviewExecutorAgent")
        session_memory = registry.get("SessionMemoryAgent")

        self.assertEqual(interview_executor.prompt_ids, ("interviewer", "followup"))
        self.assertEqual(
            interview_executor.tasks,
            ("interviewer_system_instruction", "followup_generation"),
        )
        self.assertEqual(
            session_memory.prompt_ids,
            ("candidate_profile", "conversation_summary"),
        )
        self.assertEqual(
            session_memory.tasks,
            ("session_candidate_memory_generation", "conversation_summary_generation"),
        )

    def test_all_returns_agent_definitions_sorted_by_name(self):
        registry = AgentRegistry(
            prompt_registry_with(
                prompt_definition(owner_agent="ZAgent", prompt_id="z_prompt"),
                prompt_definition(owner_agent="AAgent", prompt_id="a_prompt"),
            )
        )

        self.assertEqual(
            [definition.agent_name for definition in registry.all()],
            ["AAgent", "ZAgent"],
        )

    def test_missing_agent_raises_key_error(self):
        registry = AgentRegistry(PromptRegistry())

        with self.assertRaisesRegex(KeyError, "Agent definition not found"):
            registry.get("MissingAgent")

    def test_current_registry_validation_is_healthy(self):
        result = AgentRegistry(PromptRegistry()).validate()

        self.assertTrue(result.ok)
        self.assertEqual(result.errors, ())
        self.assertGreaterEqual(result.metadata["agent_count"], 1)
        self.assertIn("ResumeRewriteAgent", result.metadata["agent_names"])
        self.assertIn("InterviewExecutorAgent", result.metadata["multi_prompt_agents"])
        self.assertIn("SessionMemoryAgent", result.metadata["multi_prompt_agents"])

    def test_validation_rejects_duplicate_task_under_same_agent(self):
        registry = AgentRegistry(
            prompt_registry_with(
                prompt_definition(prompt_id="first_prompt", task="same_task"),
                prompt_definition(prompt_id="second_prompt", task="same_task"),
            )
        )

        result = registry.validate()

        self.assertFalse(result.ok)
        self.assertIn(
            "Agent 'TestAgent' has duplicate task binding: same_task",
            result.errors,
        )

    def test_validation_rejects_empty_required_binding_fields(self):
        registry = AgentRegistry(
            prompt_registry_with(
                prompt_definition(prompt_id="", task="", input_schema="", output_schema=""),
            )
        )

        result = registry.validate()

        self.assertFalse(result.ok)
        self.assertIn("Agent 'TestAgent' prompt '' missing prompt_id", result.errors)
        self.assertIn("Agent 'TestAgent' prompt '' missing task", result.errors)
        self.assertIn("Agent 'TestAgent' prompt '' missing input_schema", result.errors)
        self.assertIn("Agent 'TestAgent' prompt '' missing output_schema", result.errors)


if __name__ == "__main__":
    unittest.main()
