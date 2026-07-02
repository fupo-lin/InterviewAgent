from dataclasses import dataclass

from app.service.agent_run_service import AgentRunExecutor, AgentSpec
from app.service.agent_runtime import AgentRuntimeConfig, BaseAgent
from app.service.evidence_service import EvidencePacketBuilder
from app.service.interview_agent_spec_builder import InterviewAgentSpecBuilder
from app.service.llm_service import LLMService


@dataclass(frozen=True)
class SessionMemoryAgentInput:
    prompt_id: str
    session: object
    session_id: int
    previous_content: str | None
    profile_messages: list
    previous_summary_id: int | None = None


@dataclass(frozen=True)
class FirstQuestionAgentInput:
    session: object
    role_name: str
    plan_context: str | None = None
    plan: object | None = None


@dataclass(frozen=True)
class FollowupAgentInput:
    session: object
    answer_message: object
    recent_history: list
    candidate_profile: str | None = None
    conversation_summary: str | None = None
    plan_context: str | None = None
    execution_context: str | None = None
    candidate_profile_id: int | None = None
    conversation_summary_id: int | None = None
    execution: object | None = None


@dataclass(frozen=True)
class TopicJudgeAgentInput:
    session: object
    execution: object
    current_section: dict
    answer_message: object
    recent_history: list


class _InterviewSpecAgent(BaseAgent):
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


class SessionMemoryAgent(_InterviewSpecAgent):
    prompt_id = "candidate_profile"
    conversation_summary_prompt_id = "conversation_summary"

    def build_spec(self, agent_input: SessionMemoryAgentInput) -> AgentSpec:
        return self.spec_builder.memory(
            prompt_id=agent_input.prompt_id,
            session=agent_input.session,
            session_id=agent_input.session_id,
            previous_content=agent_input.previous_content,
            profile_messages=agent_input.profile_messages,
            previous_summary_id=agent_input.previous_summary_id,
        )

    async def call_model(
        self,
        agent_input: SessionMemoryAgentInput,
        spec: AgentSpec,
    ) -> tuple[str, dict | None]:
        if agent_input.prompt_id == self.prompt_id:
            return await self.llm.generate_candidate_profile(
                agent_input.previous_content,
                agent_input.profile_messages,
            )
        if agent_input.prompt_id == self.conversation_summary_prompt_id:
            return await self.llm.generate_conversation_summary(
                agent_input.previous_content,
                agent_input.profile_messages,
            )
        raise ValueError(f"Unsupported memory prompt_id: {agent_input.prompt_id}")


class InterviewExecutorAgent(_InterviewSpecAgent):
    prompt_id = "interviewer"
    followup_prompt_id = "followup"

    def build_spec(
        self,
        agent_input: FirstQuestionAgentInput | FollowupAgentInput,
    ) -> AgentSpec:
        if isinstance(agent_input, FirstQuestionAgentInput):
            return self.spec_builder.first_question(
                session=agent_input.session,
                role_name=agent_input.role_name,
                plan_context=agent_input.plan_context,
                plan=agent_input.plan,
            )
        return self.spec_builder.followup(
            session=agent_input.session,
            answer_message=agent_input.answer_message,
            recent_history=agent_input.recent_history,
            candidate_profile=agent_input.candidate_profile,
            conversation_summary=agent_input.conversation_summary,
            plan_context=agent_input.plan_context,
            execution_context=agent_input.execution_context,
            candidate_profile_id=agent_input.candidate_profile_id,
            conversation_summary_id=agent_input.conversation_summary_id,
            execution=agent_input.execution,
        )

    async def call_model(
        self,
        agent_input: FirstQuestionAgentInput | FollowupAgentInput,
        spec: AgentSpec,
    ) -> tuple[str, dict | None]:
        if isinstance(agent_input, FirstQuestionAgentInput):
            return await self.llm.generate_first_question(
                agent_input.role_name,
                plan_context=agent_input.plan_context,
            )
        return await self.llm.generate_followup(
            agent_input.session.role_name,
            agent_input.answer_message.content,
            agent_input.recent_history,
            candidate_profile=agent_input.candidate_profile,
            conversation_summary=agent_input.conversation_summary,
            plan_context=agent_input.plan_context,
            execution_context=agent_input.execution_context,
        )


class TopicJudgeAgent(_InterviewSpecAgent):
    prompt_id = "topic_completion_judge"

    def build_spec(self, agent_input: TopicJudgeAgentInput) -> AgentSpec:
        return self.spec_builder.topic_judge(
            session=agent_input.session,
            execution=agent_input.execution,
            current_section=agent_input.current_section,
            answer_message=agent_input.answer_message,
            recent_history=agent_input.recent_history,
        )

    async def call_model(
        self,
        agent_input: TopicJudgeAgentInput,
        spec: AgentSpec,
    ) -> tuple[dict, dict | None]:
        return await self.llm.judge_topic_completion(
            current_section=agent_input.current_section,
            execution_state=agent_input.execution.state or {},
            user_answer=agent_input.answer_message.content,
            recent_history=agent_input.recent_history,
        )
