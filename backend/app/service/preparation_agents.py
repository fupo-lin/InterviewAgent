from dataclasses import dataclass

from app.schemas.agent_contract import (
    GapAnalysisInputV1,
    GapAnalysisV1,
    InterviewPlanInputV1,
    InterviewPlanV1,
    JDAnalysisInputV1,
    JDAnalysisV1,
    ProjectAgentContextRefs,
    ResumeAnalysisInputV1,
    ResumeProfileV1,
)
from app.service.agent_run_service import AgentRunExecutor, AgentSpec
from app.service.agent_runtime import AgentRuntimeConfig, BaseAgent
from app.service.evidence_service import EvidencePacketBuilder
from app.service.llm_service import LLMService
from app.service.project_agent_spec_builder import ProjectAgentSpecBuilder


@dataclass(frozen=True)
class JDAnalysisAgentInput:
    project_id: int
    jd: object


@dataclass(frozen=True)
class ResumeAnalysisAgentInput:
    project_id: int
    resume: object


@dataclass(frozen=True)
class GapAnalysisAgentInput:
    project_id: int
    jd_analysis: object
    resume_profile: object


@dataclass(frozen=True)
class InterviewPlanAgentInput:
    project_id: int
    target_role: str | None
    plan_mode: str
    jd_analysis: object | None = None
    resume_profile: object | None = None
    gap_analysis: object | None = None


class _ProjectSpecAgent(BaseAgent):
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


class JDAnalysisAgent(_ProjectSpecAgent):
    prompt_id = "jd_analysis"
    input_model = JDAnalysisInputV1
    output_model = JDAnalysisV1

    def input_contract_payload(self, agent_input: JDAnalysisAgentInput) -> dict:
        return {
            "project_id": agent_input.project_id,
            "jd_id": agent_input.jd.id,
            "content_length": len(agent_input.jd.raw_content or ""),
            "has_title": bool(agent_input.jd.title),
            "has_company_name": bool(agent_input.jd.company_name),
            "has_source_url": bool(agent_input.jd.source_url),
        }

    def build_spec(self, agent_input: JDAnalysisAgentInput) -> AgentSpec:
        return self.spec_builder.jd_analysis(
            project_id=agent_input.project_id,
            jd=agent_input.jd,
        )

    async def call_model(
        self,
        agent_input: JDAnalysisAgentInput,
        spec: AgentSpec,
    ) -> tuple[dict, dict | None]:
        return await self.llm.generate_jd_analysis(agent_input.jd.raw_content)


class ResumeAnalysisAgent(_ProjectSpecAgent):
    prompt_id = "resume_analysis"
    input_model = ResumeAnalysisInputV1
    output_model = ResumeProfileV1

    def input_contract_payload(self, agent_input: ResumeAnalysisAgentInput) -> dict:
        return {
            "project_id": agent_input.project_id,
            "resume_id": agent_input.resume.id,
            "content_length": len(agent_input.resume.raw_content or ""),
            "file_name": agent_input.resume.file_name,
            "file_type": agent_input.resume.file_type,
        }

    def build_spec(self, agent_input: ResumeAnalysisAgentInput) -> AgentSpec:
        return self.spec_builder.resume_analysis(
            project_id=agent_input.project_id,
            resume=agent_input.resume,
        )

    async def call_model(
        self,
        agent_input: ResumeAnalysisAgentInput,
        spec: AgentSpec,
    ) -> tuple[dict, dict | None]:
        return await self.llm.generate_resume_profile(agent_input.resume.raw_content)


class GapAnalysisAgent(_ProjectSpecAgent):
    prompt_id = "gap_analysis"
    input_model = GapAnalysisInputV1
    output_model = GapAnalysisV1

    def input_contract_payload(self, agent_input: GapAnalysisAgentInput) -> dict:
        return {
            "project_id": agent_input.project_id,
            "jd_analysis_id": agent_input.jd_analysis.id,
            "resume_profile_id": agent_input.resume_profile.id,
            "jd_analysis_schema_version": getattr(
                agent_input.jd_analysis,
                "schema_version",
                None,
            ),
            "resume_profile_schema_version": getattr(
                agent_input.resume_profile,
                "schema_version",
                None,
            ),
        }

    def build_spec(self, agent_input: GapAnalysisAgentInput) -> AgentSpec:
        return self.spec_builder.gap_analysis(
            project_id=agent_input.project_id,
            jd_analysis=agent_input.jd_analysis,
            resume_profile=agent_input.resume_profile,
        )

    async def call_model(
        self,
        agent_input: GapAnalysisAgentInput,
        spec: AgentSpec,
    ) -> tuple[dict, dict | None]:
        return await self.llm.generate_gap_analysis(
            agent_input.jd_analysis.content,
            agent_input.resume_profile.content,
        )


class InterviewPlanAgent(_ProjectSpecAgent):
    prompt_id = "interview_plan"
    input_model = InterviewPlanInputV1
    output_model = InterviewPlanV1

    def input_contract_payload(self, agent_input: InterviewPlanAgentInput) -> dict:
        return {
            "project_id": agent_input.project_id,
            "target_role": agent_input.target_role,
            "plan_mode": agent_input.plan_mode,
            "has_jd_analysis": bool(agent_input.jd_analysis),
            "has_resume_profile": bool(agent_input.resume_profile),
            "has_gap_analysis": bool(agent_input.gap_analysis),
            "context_refs": ProjectAgentContextRefs(
                jd_analysis_id=(
                    agent_input.jd_analysis.id if agent_input.jd_analysis else None
                ),
                resume_profile_id=(
                    agent_input.resume_profile.id if agent_input.resume_profile else None
                ),
                gap_analysis_id=(
                    agent_input.gap_analysis.id if agent_input.gap_analysis else None
                ),
            ),
        }

    def build_spec(self, agent_input: InterviewPlanAgentInput) -> AgentSpec:
        return self.spec_builder.interview_plan(
            project_id=agent_input.project_id,
            target_role=agent_input.target_role,
            plan_mode=agent_input.plan_mode,
            jd_analysis=agent_input.jd_analysis,
            resume_profile=agent_input.resume_profile,
            gap_analysis=agent_input.gap_analysis,
        )

    async def call_model(
        self,
        agent_input: InterviewPlanAgentInput,
        spec: AgentSpec,
    ) -> tuple[dict, dict | None]:
        return await self.llm.generate_interview_plan(
            plan_mode=agent_input.plan_mode,
            jd_analysis=agent_input.jd_analysis.content if agent_input.jd_analysis else None,
            resume_profile=agent_input.resume_profile.content if agent_input.resume_profile else None,
            gap_analysis=agent_input.gap_analysis.content if agent_input.gap_analysis else None,
            target_role=agent_input.target_role,
        )
