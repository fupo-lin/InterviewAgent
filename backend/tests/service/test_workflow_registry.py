import unittest
from types import SimpleNamespace

from service.support import configure_backend_imports

configure_backend_imports()

from app.service.agent_registry import AgentRegistry
from app.service.prompt_registry import (
    AgentMetadata,
    PromptDefinition,
    PromptRegistry,
    WorkflowMetadata,
    WorkflowStepMetadata,
)
from app.service.workflow_registry import WorkflowRegistry


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
        "required_evidence": (),
    }
    values.update(overrides)
    return PromptDefinition(**values)


def agent_metadata(**overrides) -> AgentMetadata:
    values = {
        "agent_name": "TestAgent",
        "category": "analysis",
        "responsibility": "Test agent responsibility.",
        "owns": ("test_task",),
        "not_responsible_for": ("runtime execution",),
    }
    values.update(overrides)
    return AgentMetadata(**values)


def workflow_step(**overrides) -> WorkflowStepMetadata:
    values = {
        "step_id": "test_step",
        "agent_name": "TestAgent",
        "prompt_id": "test_prompt",
        "task": "test_task",
        "required": True,
        "depends_on": (),
    }
    values.update(overrides)
    return WorkflowStepMetadata(**values)


def workflow_metadata(**overrides) -> WorkflowMetadata:
    values = {
        "workflow_id": "test_workflow",
        "name": "Test Workflow",
        "description": "Workflow registry test workflow.",
        "steps": (workflow_step(),),
    }
    values.update(overrides)
    return WorkflowMetadata(**values)


def prompt_registry_with(
    definitions: tuple[PromptDefinition, ...] | None = None,
    agents: tuple[AgentMetadata, ...] | None = None,
    workflows: tuple[WorkflowMetadata, ...] | None = None,
):
    return SimpleNamespace(
        all=lambda: tuple(definitions or (prompt_definition(),)),
        get=lambda prompt_id: _get_prompt(prompt_id, tuple(definitions or (prompt_definition(),))),
        all_agent_metadata=lambda: tuple(agents or (agent_metadata(),)),
        all_workflow_metadata=lambda: tuple(workflows or (workflow_metadata(),)),
    )


def _get_prompt(prompt_id: str, definitions: tuple[PromptDefinition, ...]) -> PromptDefinition:
    for definition in definitions:
        if definition.prompt_id == prompt_id:
            return definition
    raise KeyError(f"Prompt definition not found: {prompt_id}")


class WorkflowRegistryTest(unittest.TestCase):
    def test_current_manifest_builds_workflow_definitions(self):
        registry = WorkflowRegistry(PromptRegistry(), AgentRegistry(PromptRegistry()))

        definition = registry.get("resume_optimization")

        self.assertEqual(definition.workflow_id, "resume_optimization")
        self.assertEqual(definition.step_ids, ("resume_authenticity", "resume_rewrite"))
        self.assertEqual(
            definition.agent_names,
            ("ResumeAuthenticityAgent", "ResumeRewriteAgent"),
        )
        self.assertEqual(definition.prompt_ids, ("resume_authenticity", "resume_rewrite"))
        self.assertEqual(definition.steps[-1].depends_on, ("resume_authenticity",))
        self.assertTrue(definition.steps[-1].required)

    def test_current_registry_validation_is_healthy(self):
        prompt_registry = PromptRegistry()
        result = WorkflowRegistry(prompt_registry, AgentRegistry(prompt_registry)).validate()

        self.assertTrue(result.ok)
        self.assertEqual(result.errors, ())
        self.assertGreaterEqual(result.metadata["workflow_count"], 1)
        self.assertIn("preparation", result.metadata["workflow_ids"])
        self.assertIn("resume_optimization", result.metadata["workflow_ids"])

    def test_get_missing_workflow_raises_key_error(self):
        registry = WorkflowRegistry(PromptRegistry(), AgentRegistry(PromptRegistry()))

        with self.assertRaisesRegex(KeyError, "Workflow definition not found"):
            registry.get("missing_workflow")

    def test_validation_rejects_duplicate_step_ids(self):
        prompts = prompt_registry_with(
            workflows=(
                workflow_metadata(
                    steps=(
                        workflow_step(step_id="same_step"),
                        workflow_step(step_id="same_step"),
                    )
                ),
            )
        )
        registry = WorkflowRegistry(prompts, AgentRegistry(prompts))

        result = registry.validate()

        self.assertFalse(result.ok)
        self.assertIn("Workflow 'test_workflow' has duplicate step_id: same_step", result.errors)

    def test_validation_rejects_unknown_dependency(self):
        prompts = prompt_registry_with(
            workflows=(
                workflow_metadata(
                    steps=(
                        workflow_step(depends_on=("missing_step",)),
                    )
                ),
            )
        )
        registry = WorkflowRegistry(prompts, AgentRegistry(prompts))

        result = registry.validate()

        self.assertFalse(result.ok)
        self.assertIn(
            "Workflow 'test_workflow' step 'test_step' depends on unknown step: missing_step",
            result.errors,
        )

    def test_validation_rejects_unknown_agent_and_prompt(self):
        prompts = prompt_registry_with(
            workflows=(
                workflow_metadata(
                    steps=(
                        workflow_step(agent_name="MissingAgent", prompt_id="missing_prompt"),
                    )
                ),
            )
        )
        registry = WorkflowRegistry(prompts, AgentRegistry(prompts))

        result = registry.validate()

        self.assertFalse(result.ok)
        self.assertIn(
            "Workflow 'test_workflow' step 'test_step' references unknown agent: MissingAgent",
            result.errors,
        )
        self.assertIn(
            "Workflow 'test_workflow' step 'test_step' references unknown prompt: missing_prompt",
            result.errors,
        )

    def test_validation_rejects_agent_prompt_task_mismatch(self):
        prompts = prompt_registry_with(
            definitions=(
                prompt_definition(prompt_id="first_prompt", task="first_task"),
                prompt_definition(
                    prompt_id="second_prompt",
                    owner_agent="SecondAgent",
                    task="second_task",
                ),
            ),
            agents=(
                agent_metadata(owns=("first_task",)),
                agent_metadata(
                    agent_name="SecondAgent",
                    owns=("second_task",),
                ),
            ),
            workflows=(
                workflow_metadata(
                    steps=(
                        workflow_step(
                            agent_name="TestAgent",
                            prompt_id="second_prompt",
                            task="wrong_task",
                        ),
                    )
                ),
            ),
        )
        registry = WorkflowRegistry(prompts, AgentRegistry(prompts))

        result = registry.validate()

        self.assertFalse(result.ok)
        self.assertIn(
            "Workflow 'test_workflow' step 'test_step' prompt is not bound to agent: second_prompt",
            result.errors,
        )
        self.assertIn(
            "Workflow 'test_workflow' step 'test_step' task is not owned by agent: wrong_task",
            result.errors,
        )
        self.assertIn(
            "Workflow 'test_workflow' step 'test_step' agent mismatch: "
            "workflow=TestAgent, prompt=SecondAgent",
            result.errors,
        )
        self.assertIn(
            "Workflow 'test_workflow' step 'test_step' task mismatch: "
            "workflow=wrong_task, prompt=second_task",
            result.errors,
        )

    def test_validation_rejects_cyclic_dependency(self):
        prompts = prompt_registry_with(
            workflows=(
                workflow_metadata(
                    steps=(
                        workflow_step(step_id="a", depends_on=("b",)),
                        workflow_step(step_id="b", depends_on=("a",)),
                    )
                ),
            )
        )
        registry = WorkflowRegistry(prompts, AgentRegistry(prompts))

        result = registry.validate()

        self.assertFalse(result.ok)
        self.assertIn(
            "Workflow 'test_workflow' has cyclic dependency: a -> b -> a",
            result.errors,
        )


if __name__ == "__main__":
    unittest.main()
