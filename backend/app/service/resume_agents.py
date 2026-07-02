from dataclasses import dataclass

from app.schemas.agent_contract import (
    ProjectAgentContextRefs,
    ResumeAuthenticityInputV1,
    ResumeAuthenticityReportV1,
    ResumeRewriteInputV1,
    ResumeRewriteResultV1,
)
from app.service.agent_run_service import AgentRunExecutor, AgentSpec
from app.service.agent_runtime import AgentRuntimeConfig, BaseAgent
from app.service.evidence_service import EvidencePacketBuilder
from app.service.llm_service import LLMService
from app.service.project_agent_spec_builder import ProjectAgentContext, ProjectAgentSpecBuilder


@dataclass(frozen=True)
class ResumeAuthenticityAgentInput:
    project_id: int
    resume_id: int
    resume_content: str
    session_id: int | None
    execution_state: dict | None
    evaluation: dict | None
    transcript_messages: list | None
    context: ProjectAgentContext


@dataclass(frozen=True)
class ResumeRewriteAgentInput:
    project_id: int
    resume_id: int
    resume_content: str
    rewrite_mode: str
    authenticity_report_id: int | None
    resume_authenticity: dict | None
    execution_state: dict | None
    evaluation: dict | None
    transcript_messages: list | None
    context: ProjectAgentContext


class ResumeAuthenticityAgent(BaseAgent[ResumeAuthenticityAgentInput]):
    prompt_id = "resume_authenticity"
    input_model = ResumeAuthenticityInputV1
    output_model = ResumeAuthenticityReportV1

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

    def input_contract_payload(self, agent_input: ResumeAuthenticityAgentInput) -> dict:
        context = agent_input.context
        return {
            "project_id": agent_input.project_id,
            "resume_id": agent_input.resume_id,
            "resume_content": agent_input.resume_content,
            "session_id": agent_input.session_id,
            "execution_state": agent_input.execution_state,
            "evaluation": agent_input.evaluation,
            "transcript_messages": agent_input.transcript_messages,
            "context_refs": ProjectAgentContextRefs(
                jd_analysis_id=context.jd_analysis.id if context.jd_analysis else None,
                resume_profile_id=context.resume_profile.id if context.resume_profile else None,
                gap_analysis_id=context.gap_analysis.id if context.gap_analysis else None,
                project_candidate_profile_id=(
                    context.candidate_profile.id if context.candidate_profile else None
                ),
            ),
        }

    def build_spec(self, agent_input: ResumeAuthenticityAgentInput) -> AgentSpec:
        return self.spec_builder.resume_authenticity(
            project_id=agent_input.project_id,
            resume_id=agent_input.resume_id,
            session_id=agent_input.session_id,
            execution_state=agent_input.execution_state,
            transcript_messages=agent_input.transcript_messages,
            context=agent_input.context,
        )

    async def call_model(
        self,
        agent_input: ResumeAuthenticityAgentInput,
        spec: AgentSpec,
    ) -> tuple[dict, dict | None]:
        context = agent_input.context
        return await self.llm.generate_resume_authenticity_report(
            resume_content=agent_input.resume_content,
            resume_profile=context.resume_profile.content if context.resume_profile else None,
            jd_analysis=context.jd_analysis.content if context.jd_analysis else None,
            gap_analysis=context.gap_analysis.content if context.gap_analysis else None,
            project_candidate_profile=(
                context.candidate_profile.content if context.candidate_profile else None
            ),
            execution_state=agent_input.execution_state,
            evaluation=agent_input.evaluation,
            transcript_messages=agent_input.transcript_messages or [],
            evidence_packet=spec.evidence_packet,
        )


class ResumeRewriteAgent(BaseAgent[ResumeRewriteAgentInput]):
    prompt_id = "resume_rewrite"
    input_model = ResumeRewriteInputV1
    output_model = ResumeRewriteResultV1

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

    def input_contract_payload(self, agent_input: ResumeRewriteAgentInput) -> dict:
        context = agent_input.context
        return {
            "project_id": agent_input.project_id,
            "resume_id": agent_input.resume_id,
            "resume_content": agent_input.resume_content,
            "rewrite_mode": agent_input.rewrite_mode,
            "authenticity_report_id": agent_input.authenticity_report_id,
            "resume_authenticity": agent_input.resume_authenticity,
            "execution_state": agent_input.execution_state,
            "evaluation": agent_input.evaluation,
            "transcript_messages": agent_input.transcript_messages,
            "context_refs": ProjectAgentContextRefs(
                jd_analysis_id=context.jd_analysis.id if context.jd_analysis else None,
                resume_profile_id=context.resume_profile.id if context.resume_profile else None,
                gap_analysis_id=context.gap_analysis.id if context.gap_analysis else None,
                project_candidate_profile_id=(
                    context.candidate_profile.id if context.candidate_profile else None
                ),
            ),
        }

    def build_spec(self, agent_input: ResumeRewriteAgentInput) -> AgentSpec:
        return self.spec_builder.resume_rewrite(
            project_id=agent_input.project_id,
            resume_id=agent_input.resume_id,
            rewrite_mode=agent_input.rewrite_mode,
            authenticity_report_id=agent_input.authenticity_report_id,
            resume_authenticity=agent_input.resume_authenticity,
            execution_state=agent_input.execution_state,
            transcript_messages=agent_input.transcript_messages,
            context=agent_input.context,
        )

    async def call_model(
        self,
        agent_input: ResumeRewriteAgentInput,
        spec: AgentSpec,
    ) -> tuple[dict, dict | None]:
        context = agent_input.context
        return await self.llm.generate_resume_rewrite(
            rewrite_mode=agent_input.rewrite_mode,
            resume_content=agent_input.resume_content,
            resume_profile=context.resume_profile.content if context.resume_profile else None,
            jd_analysis=context.jd_analysis.content if context.jd_analysis else None,
            gap_analysis=context.gap_analysis.content if context.gap_analysis else None,
            project_candidate_profile=(
                context.candidate_profile.content if context.candidate_profile else None
            ),
            resume_authenticity=agent_input.resume_authenticity,
            evaluation=agent_input.evaluation,
            execution_state=agent_input.execution_state,
            evidence_packet=spec.evidence_packet,
        )
