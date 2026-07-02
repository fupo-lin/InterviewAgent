from dataclasses import dataclass

from app.service.agent_registry import AgentDefinition, AgentRegistry, agent_registry
from app.service.prompt_manifest_validator import GovernanceCheckResult
from app.service.workflow_registry import WorkflowRegistry, workflow_registry


@dataclass(frozen=True)
class ArtifactBoundaryDefinition:
    artifact_kind: str
    owner_agent: str
    agent_category: str
    scope: str
    lifecycle: str
    storage_model: str
    output_schemas: tuple[str, ...]
    allowed_workflows: tuple[str, ...]
    allowed_downstream_usage: tuple[str, ...]
    not_allowed_usage: tuple[str, ...]
    description: str


BOUNDARY_DEFINITIONS: tuple[ArtifactBoundaryDefinition, ...] = (
    ArtifactBoundaryDefinition(
        artifact_kind="memory",
        owner_agent="SessionMemoryAgent",
        agent_category="memory",
        scope="session",
        lifecycle="rolling",
        storage_model="InterviewSummary",
        output_schemas=("SessionCandidateMemory.v1", "ConversationSummary.v1"),
        allowed_workflows=("interview_runtime",),
        allowed_downstream_usage=(
            "interview runtime context compression",
            "near-term conversation continuity",
        ),
        not_allowed_usage=(
            "project-level capability model",
            "final interview evaluation",
            "authoritative resume rewrite evidence",
        ),
        description=(
            "Session-scoped memory generated from transcript deltas. "
            "It may summarize conversation and candidate signals inside one interview session, "
            "but it is not the project-level candidate capability model."
        ),
    ),
    ArtifactBoundaryDefinition(
        artifact_kind="profile",
        owner_agent="ProjectCandidateProfileAgent",
        agent_category="profile",
        scope="project",
        lifecycle="versioned",
        storage_model="ProjectCandidateProfile",
        output_schemas=("ProjectCandidateProfile.v1",),
        allowed_workflows=("post_interview_assessment",),
        allowed_downstream_usage=(
            "resume authenticity assessment",
            "resume rewrite context",
            "project-level candidate capability modeling",
        ),
        not_allowed_usage=(
            "session memory replacement",
            "final interview score",
            "raw transcript compression",
        ),
        description=(
            "Project-level candidate capability model. It is versioned and can combine "
            "resume, interview, evaluation, and evidence signals."
        ),
    ),
    ArtifactBoundaryDefinition(
        artifact_kind="evaluation",
        owner_agent="EvaluationAgent",
        agent_category="evaluation",
        scope="session",
        lifecycle="final",
        storage_model="InterviewEvaluation",
        output_schemas=("InterviewEvaluation.v1",),
        allowed_workflows=("post_interview_assessment",),
        allowed_downstream_usage=(
            "project candidate profile generation",
            "post-interview assessment reporting",
        ),
        not_allowed_usage=(
            "session memory replacement",
            "resume authenticity judgement",
            "resume rewrite as direct evidence",
        ),
        description=(
            "Final interview evaluation for one session. It evaluates performance, "
            "but it is not memory and not the long-lived project capability profile."
        ),
    ),
)


class ArtifactBoundaryRegistry:
    def __init__(
        self,
        definitions: tuple[ArtifactBoundaryDefinition, ...] = BOUNDARY_DEFINITIONS,
    ) -> None:
        self._definitions = {
            definition.artifact_kind: definition
            for definition in definitions
        }

    def get(self, artifact_kind: str) -> ArtifactBoundaryDefinition:
        definition = self._definitions.get(artifact_kind)
        if not definition:
            raise KeyError(f"Artifact boundary definition not found: {artifact_kind}")
        return definition

    def all(self) -> tuple[ArtifactBoundaryDefinition, ...]:
        return tuple(self._definitions[artifact_kind] for artifact_kind in sorted(self._definitions))

    def by_owner_agent(self, owner_agent: str) -> ArtifactBoundaryDefinition | None:
        for definition in self.all():
            if definition.owner_agent == owner_agent:
                return definition
        return None


class ArtifactBoundaryValidator:
    def __init__(
        self,
        boundaries: ArtifactBoundaryRegistry | None = None,
        agents: AgentRegistry = agent_registry,
        workflows: WorkflowRegistry = workflow_registry,
    ) -> None:
        self.boundaries = boundaries or artifact_boundary_registry
        self.agents = agents
        self.workflows = workflows

    def validate(self) -> GovernanceCheckResult:
        errors: list[str] = []
        warnings: list[str] = []

        for boundary in self.boundaries.all():
            self._validate_boundary_agent(boundary, errors)
            self._validate_boundary_workflows(boundary, errors, warnings)

        metadata = {
            "artifact_kinds": [definition.artifact_kind for definition in self.boundaries.all()],
            "owner_agents": [definition.owner_agent for definition in self.boundaries.all()],
            "storage_models": [definition.storage_model for definition in self.boundaries.all()],
        }
        return GovernanceCheckResult(
            ok=not errors,
            errors=tuple(errors),
            warnings=tuple(warnings),
            metadata=metadata,
        )

    def _validate_boundary_agent(
        self,
        boundary: ArtifactBoundaryDefinition,
        errors: list[str],
    ) -> None:
        prefix = f"Artifact boundary '{boundary.artifact_kind}'"
        try:
            agent = self.agents.get(boundary.owner_agent)
        except KeyError:
            errors.append(f"{prefix} references missing owner_agent: {boundary.owner_agent}")
            return

        if agent.category != boundary.agent_category:
            errors.append(
                f"{prefix} category mismatch: "
                f"boundary={boundary.agent_category}, agent={agent.category}"
            )
        missing_schemas = [
            schema
            for schema in boundary.output_schemas
            if schema not in agent.output_schemas
        ]
        for schema in missing_schemas:
            errors.append(f"{prefix} output_schema is not produced by owner_agent: {schema}")

    def _validate_boundary_workflows(
        self,
        boundary: ArtifactBoundaryDefinition,
        errors: list[str],
        warnings: list[str],
    ) -> None:
        seen_in_workflows = []
        for workflow in self.workflows.all():
            matching_steps = [
                step
                for step in workflow.steps
                if step.agent_name == boundary.owner_agent
            ]
            if not matching_steps:
                continue
            seen_in_workflows.append(workflow.workflow_id)
            if workflow.workflow_id not in boundary.allowed_workflows:
                errors.append(
                    f"Artifact boundary '{boundary.artifact_kind}' owner_agent "
                    f"appears in disallowed workflow: {workflow.workflow_id}"
                )

        for workflow_id in boundary.allowed_workflows:
            try:
                self.workflows.get(workflow_id)
            except KeyError:
                errors.append(
                    f"Artifact boundary '{boundary.artifact_kind}' references missing workflow: {workflow_id}"
                )

        if not seen_in_workflows:
            warnings.append(
                f"Artifact boundary '{boundary.artifact_kind}' owner_agent does not appear in any workflow"
            )


artifact_boundary_registry = ArtifactBoundaryRegistry()
