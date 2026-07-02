import unittest
from types import SimpleNamespace

from service.support import configure_backend_imports

configure_backend_imports()

from app.service.agent_registry import AgentRegistry
from app.service.artifact_boundary import (
    ArtifactBoundaryDefinition,
    ArtifactBoundaryRegistry,
    ArtifactBoundaryValidator,
)
from app.service.prompt_registry import AgentMetadata, PromptDefinition, PromptRegistry
from app.service.workflow_registry import WorkflowRegistry


def prompt_definition(**overrides) -> PromptDefinition:
    values = {
        "prompt_id": "candidate_profile",
        "prompt_file": "candidate_profile.txt",
        "version": "3.0.0",
        "owner_agent": "SessionMemoryAgent",
        "task": "session_candidate_memory_generation",
        "input_schema": "SessionCandidateMemoryInput.v1",
        "output_schema": "SessionCandidateMemory.v1",
        "required_context": ("InterviewTranscriptDelta",),
        "optional_context": ("PreviousCandidateMemory",),
        "required_evidence": ("interview_answer",),
    }
    values.update(overrides)
    return PromptDefinition(**values)


class ArtifactBoundaryTest(unittest.TestCase):
    def test_current_boundaries_are_healthy(self):
        prompt_registry = PromptRegistry()
        agent_registry = AgentRegistry(prompt_registry)
        workflow_registry = WorkflowRegistry(prompt_registry, agent_registry)

        result = ArtifactBoundaryValidator(
            agents=agent_registry,
            workflows=workflow_registry,
        ).validate()

        self.assertTrue(result.ok)
        self.assertEqual(result.errors, ())
        self.assertIn("memory", result.metadata["artifact_kinds"])
        self.assertIn("profile", result.metadata["artifact_kinds"])
        self.assertIn("evaluation", result.metadata["artifact_kinds"])
        self.assertIn("InterviewSummary", result.metadata["storage_models"])

    def test_registry_returns_boundaries_by_kind_and_owner(self):
        registry = ArtifactBoundaryRegistry()

        memory = registry.get("memory")
        by_owner = registry.by_owner_agent("SessionMemoryAgent")
        candidate_profile_context = registry.context("CandidateProfile")
        project_profile_context = registry.context("ProjectCandidateProfile")

        self.assertEqual(memory.owner_agent, "SessionMemoryAgent")
        self.assertEqual(memory.scope, "session")
        self.assertEqual(memory.lifecycle, "rolling")
        self.assertEqual(memory.storage_model, "InterviewSummary")
        self.assertEqual(by_owner.artifact_kind, "memory")
        self.assertEqual(candidate_profile_context.artifact_kind, "memory")
        self.assertEqual(candidate_profile_context.scope, "session")
        self.assertEqual(project_profile_context.artifact_kind, "profile")
        self.assertEqual(project_profile_context.scope, "project")

    def test_missing_boundary_raises_key_error(self):
        registry = ArtifactBoundaryRegistry()

        with self.assertRaisesRegex(KeyError, "Artifact boundary definition not found"):
            registry.get("missing")

    def test_validator_rejects_agent_category_mismatch(self):
        prompt_registry = _prompt_registry(
            prompts=(prompt_definition(),),
            agents=(
                AgentMetadata(
                    agent_name="SessionMemoryAgent",
                    category="profile",
                    responsibility="Wrong category.",
                    owns=("session_candidate_memory_generation",),
                    not_responsible_for=("project profile",),
                ),
            ),
            workflows=(),
        )
        boundaries = ArtifactBoundaryRegistry(
            definitions=(
                ArtifactBoundaryDefinition(
                    artifact_kind="memory",
                    owner_agent="SessionMemoryAgent",
                    agent_category="memory",
                    scope="session",
                    lifecycle="rolling",
                    storage_model="InterviewSummary",
                    output_schemas=("SessionCandidateMemory.v1",),
                    allowed_workflows=(),
                    allowed_downstream_usage=(),
                    not_allowed_usage=(),
                    description="Memory boundary.",
                ),
            )
        )

        result = ArtifactBoundaryValidator(
            boundaries=boundaries,
            agents=AgentRegistry(prompt_registry),
            workflows=WorkflowRegistry(prompt_registry, AgentRegistry(prompt_registry)),
        ).validate()

        self.assertFalse(result.ok)
        self.assertIn(
            "Artifact boundary 'memory' category mismatch: boundary=memory, agent=profile",
            result.errors,
        )

    def test_validator_rejects_disallowed_workflow_usage(self):
        prompt_registry = PromptRegistry()
        agent_registry = AgentRegistry(prompt_registry)
        boundaries = ArtifactBoundaryRegistry(
            definitions=(
                ArtifactBoundaryDefinition(
                    artifact_kind="memory",
                    owner_agent="SessionMemoryAgent",
                    agent_category="memory",
                    scope="session",
                    lifecycle="rolling",
                    storage_model="InterviewSummary",
                    output_schemas=("SessionCandidateMemory.v1", "ConversationSummary.v1"),
                    allowed_workflows=("post_interview_assessment",),
                    allowed_downstream_usage=(),
                    not_allowed_usage=(),
                    description="Memory boundary.",
                ),
            )
        )

        result = ArtifactBoundaryValidator(
            boundaries=boundaries,
            agents=agent_registry,
            workflows=WorkflowRegistry(prompt_registry, agent_registry),
        ).validate()

        self.assertFalse(result.ok)
        self.assertIn(
            "Artifact boundary 'memory' owner_agent appears in disallowed workflow: interview_runtime",
            result.errors,
        )

    def test_validator_rejects_memory_agent_using_project_profile_context(self):
        prompt_registry = _prompt_registry(
            prompts=(
                prompt_definition(
                    optional_context=("ProjectCandidateProfile",),
                ),
            ),
            agents=(
                AgentMetadata(
                    agent_name="SessionMemoryAgent",
                    category="memory",
                    responsibility="Maintain session memory.",
                    owns=("session_candidate_memory_generation",),
                    not_responsible_for=("project profile",),
                ),
            ),
            workflows=(),
        )

        result = ArtifactBoundaryValidator(
            agents=AgentRegistry(prompt_registry),
            workflows=WorkflowRegistry(prompt_registry, AgentRegistry(prompt_registry)),
        ).validate()

        self.assertFalse(result.ok)
        self.assertIn(
            "Agent 'SessionMemoryAgent' memory prompt uses non-memory context "
            "'ProjectCandidateProfile' (profile)",
            result.errors,
        )


def _prompt_registry(prompts, agents, workflows):
    return SimpleNamespace(
        all=lambda: tuple(prompts),
        get=lambda prompt_id: _get_prompt(prompt_id, tuple(prompts)),
        all_agent_metadata=lambda: tuple(agents),
        all_workflow_metadata=lambda: tuple(workflows),
    )


def _get_prompt(prompt_id: str, prompts: tuple[PromptDefinition, ...]) -> PromptDefinition:
    for prompt in prompts:
        if prompt.prompt_id == prompt_id:
            return prompt
    raise KeyError(f"Prompt definition not found: {prompt_id}")


if __name__ == "__main__":
    unittest.main()
