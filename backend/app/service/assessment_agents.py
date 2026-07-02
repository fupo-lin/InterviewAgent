from dataclasses import dataclass

from app.service.agent_run_service import AgentRunExecutor, AgentSpec
from app.service.agent_runtime import AgentRuntimeConfig, BaseAgent
from app.service.evidence_service import EvidencePacketBuilder
from app.service.interview_agent_spec_builder import InterviewAgentSpecBuilder
from app.service.llm_service import LLMService
from app.service.project_agent_spec_builder import ProjectAgentContext, ProjectAgentSpecBuilder


@dataclass(frozen=True)
class EvaluationAgentInput:
    session: object
    history: list
    full_history: list
    execution: object | None
    candidate_profile: object | None
    conversation_summary: object | None
    plan_context: str | None = None


@dataclass(frozen=True)
class ProjectCandidateProfileAgentInput:
    project_id: int
    target_role: str | None
    source_session_id: int | None
    execution_state: dict | None
    evaluation: dict | None
    transcript_messages: list | None
    context: ProjectAgentContext


class EvaluationAgent(BaseAgent[EvaluationAgentInput]):
    prompt_id = "evaluation"

    def __init__(
        self,
        agent_run_executor: AgentRunExecutor,
        evidence_builder: EvidencePacketBuilder,
        llm: LLMService,
        config: AgentRuntimeConfig,
    ) -> None:
        super().__init__(agent_run_executor, config)
        self.llm = llm
        self.spec_builder = InterviewAgentSpecBuilder(
            agent_run_executor=agent_run_executor,
            evidence_builder=evidence_builder,
        )

    def build_spec(self, agent_input: EvaluationAgentInput) -> AgentSpec:
        return self.spec_builder.evaluation(
            session=agent_input.session,
            history=agent_input.history,
            full_history=agent_input.full_history,
            execution=agent_input.execution,
            candidate_profile=agent_input.candidate_profile,
            conversation_summary=agent_input.conversation_summary,
        )

    async def call_model(
        self,
        agent_input: EvaluationAgentInput,
        spec: AgentSpec,
    ) -> tuple[dict[str, str], dict | None]:
        return await self.llm.generate_evaluation(
            agent_input.history,
            candidate_profile=(
                agent_input.candidate_profile.content if agent_input.candidate_profile else None
            ),
            conversation_summary=(
                agent_input.conversation_summary.content
                if agent_input.conversation_summary
                else None
            ),
            plan_context=agent_input.plan_context,
            evidence_packet=spec.evidence_packet,
        )


class ProjectCandidateProfileAgent(BaseAgent[ProjectCandidateProfileAgentInput]):
    prompt_id = "project_candidate_profile"

    def __init__(
        self,
        agent_run_executor: AgentRunExecutor,
        evidence_builder: EvidencePacketBuilder,
        llm: LLMService,
        config: AgentRuntimeConfig,
    ) -> None:
        super().__init__(agent_run_executor, config)
        self.llm = llm
        self.spec_builder = ProjectAgentSpecBuilder(
            agent_run_executor=agent_run_executor,
            evidence_builder=evidence_builder,
        )

    def build_spec(self, agent_input: ProjectCandidateProfileAgentInput) -> AgentSpec:
        return self.spec_builder.project_candidate_profile(
            project_id=agent_input.project_id,
            target_role=agent_input.target_role,
            source_session_id=agent_input.source_session_id,
            execution_state=agent_input.execution_state,
            evaluation=agent_input.evaluation,
            transcript_messages=agent_input.transcript_messages,
            context=agent_input.context,
        )

    async def call_model(
        self,
        agent_input: ProjectCandidateProfileAgentInput,
        spec: AgentSpec,
    ) -> tuple[dict, dict | None]:
        context = agent_input.context
        return await self.llm.generate_project_candidate_profile(
            target_role=agent_input.target_role,
            jd_analysis=context.jd_analysis.content if context.jd_analysis else None,
            resume_profile=context.resume_profile.content if context.resume_profile else None,
            gap_analysis=context.gap_analysis.content if context.gap_analysis else None,
            execution_state=agent_input.execution_state,
            evaluation=agent_input.evaluation,
            transcript_messages=agent_input.transcript_messages or [],
            evidence_packet=spec.evidence_packet,
        )
