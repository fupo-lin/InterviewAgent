from dataclasses import dataclass

from app.schemas.agent_contract import (
    InterviewExecutorInputV1,
    InterviewQuestionOutputV1,
    SessionMemoryInputV1,
    SessionMemoryOutputV1,
    TopicJudgeInputV1,
    TopicJudgeResultV1,
)
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
    input_model = SessionMemoryInputV1
    output_model = SessionMemoryOutputV1

    def input_contract_payload(self, agent_input: SessionMemoryAgentInput) -> dict:
        messages = agent_input.profile_messages or []
        return {
            "prompt_id": agent_input.prompt_id,
            "session_id": agent_input.session_id,
            "project_id": agent_input.session.project_id if agent_input.session else None,
            "previous_summary_id": agent_input.previous_summary_id,
            "message_count": len(messages),
            "from_round_no": messages[0].round_no if messages else None,
            "to_round_no": messages[-1].round_no if messages else None,
            "has_previous_content": bool(agent_input.previous_content),
        }

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
    input_model = InterviewExecutorInputV1
    output_model = InterviewQuestionOutputV1

    def input_contract_payload(
        self,
        agent_input: FirstQuestionAgentInput | FollowupAgentInput,
    ) -> dict:
        if isinstance(agent_input, FirstQuestionAgentInput):
            session = agent_input.session
            return {
                "step_id": "first_question",
                "session_id": session.id,
                "project_id": session.project_id,
                "role_name": agent_input.role_name,
                "interview_plan_id": agent_input.plan.id
                if agent_input.plan
                else session.interview_plan_id,
                "recent_history_count": 0,
                "has_plan_context": bool(agent_input.plan_context),
            }

        session = agent_input.session
        answer_message = agent_input.answer_message
        return {
            "step_id": "followup",
            "session_id": session.id,
            "project_id": session.project_id,
            "role_name": session.role_name,
            "interview_plan_id": session.interview_plan_id,
            "answer_message_id": answer_message.id,
            "answer_content_length": len(answer_message.content or ""),
            "round_no": answer_message.round_no,
            "recent_history_count": len(agent_input.recent_history or []),
            "has_candidate_profile": bool(agent_input.candidate_profile),
            "has_conversation_summary": bool(agent_input.conversation_summary),
            "has_plan_context": bool(agent_input.plan_context),
            "has_execution_context": bool(agent_input.execution_context),
            "candidate_profile_summary_id": agent_input.candidate_profile_id,
            "conversation_summary_id": agent_input.conversation_summary_id,
            "execution_id": agent_input.execution.id if agent_input.execution else None,
        }

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
    input_model = TopicJudgeInputV1
    output_model = TopicJudgeResultV1

    def input_contract_payload(self, agent_input: TopicJudgeAgentInput) -> dict:
        section = agent_input.current_section or {}
        answer_message = agent_input.answer_message
        return {
            "session_id": agent_input.session.id,
            "project_id": agent_input.session.project_id,
            "interview_plan_id": agent_input.session.interview_plan_id,
            "execution_id": agent_input.execution.id,
            "answer_message_id": answer_message.id,
            "answer_content_length": len(answer_message.content or ""),
            "round_no": answer_message.round_no,
            "current_section_key": section.get("section_key"),
            "current_section_completed_rounds": section.get("completed_rounds"),
            "current_section_target_rounds": section.get("target_rounds"),
            "probe_point_count": len(section.get("probe_points") or []),
            "uncovered_probe_point_count": len(section.get("uncovered_probe_points") or []),
            "recent_history_count": len(agent_input.recent_history or []),
        }

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
