from app.service.agent_run_service import AgentRunExecutor, AgentSpec
from app.service.evidence_service import EvidencePacketBuilder


class InterviewAgentSpecBuilder:
    def __init__(
        self,
        agent_run_executor: AgentRunExecutor,
        evidence_builder: EvidencePacketBuilder,
    ) -> None:
        self.agent_run_executor = agent_run_executor
        self.evidence_builder = evidence_builder

    def evaluation(
        self,
        session,
        history: list,
        full_history: list,
        execution,
        candidate_profile,
        conversation_summary,
    ) -> AgentSpec:
        evidence_packet = self.evidence_builder.build_evaluation_packet(
            session_id=session.id,
            project_id=session.project_id,
            execution_state=execution.state if execution else None,
            transcript_messages=full_history,
        )
        return self.agent_run_executor.spec(
            prompt_id="evaluation",
            project_id=session.project_id,
            session_id=session.id,
            input_snapshot={
                "history_message_count": len(history),
                "full_history_message_count": len(full_history),
                "has_candidate_profile": bool(candidate_profile),
                "has_conversation_summary": bool(conversation_summary),
                "has_interview_plan": bool(session.interview_plan_id),
            },
            context_refs={
                "candidate_profile_summary_id": candidate_profile.id if candidate_profile else None,
                "conversation_summary_id": conversation_summary.id if conversation_summary else None,
                "interview_plan_id": session.interview_plan_id,
                "execution_id": execution.id if execution else None,
            },
            evidence_packet=evidence_packet,
        )

    def first_question(
        self,
        session,
        role_name: str,
        plan_context: str | None = None,
        plan=None,
    ) -> AgentSpec:
        prompt_id = "interviewer"
        definition = self.agent_run_executor.definition(prompt_id)
        evidence_packet = self.evidence_builder.build_question_generation_packet(
            task=definition.task,
            session_id=session.id,
            project_id=session.project_id,
        )
        return self.agent_run_executor.spec(
            prompt_id=prompt_id,
            project_id=session.project_id,
            session_id=session.id,
            input_snapshot={
                "role_name": role_name,
                "has_plan_context": bool(plan_context),
            },
            context_refs={
                "interview_plan_id": plan.id if plan else session.interview_plan_id,
            },
            evidence_packet=evidence_packet,
            output_snapshot=lambda output: {"reply": output},
        )

    def followup(
        self,
        session,
        answer_message,
        recent_history: list,
        candidate_profile: str | None = None,
        conversation_summary: str | None = None,
        plan_context: str | None = None,
        execution_context: str | None = None,
        candidate_profile_id: int | None = None,
        conversation_summary_id: int | None = None,
        execution=None,
    ) -> AgentSpec:
        prompt_id = "followup"
        definition = self.agent_run_executor.definition(prompt_id)
        evidence_packet = self.evidence_builder.build_question_generation_packet(
            task=definition.task,
            session_id=session.id,
            project_id=session.project_id,
            user_answer_message_id=answer_message.id,
            user_answer=answer_message.content,
            round_no=answer_message.round_no,
            recent_history=recent_history,
            execution_state=execution.state if execution else None,
        )
        return self.agent_run_executor.spec(
            prompt_id=prompt_id,
            project_id=session.project_id,
            session_id=session.id,
            input_snapshot={
                "role_name": session.role_name,
                "answer_message_id": answer_message.id,
                "round_no": answer_message.round_no,
                "recent_history_count": len(recent_history or []),
                "has_candidate_profile": bool(candidate_profile),
                "has_conversation_summary": bool(conversation_summary),
                "has_plan_context": bool(plan_context),
                "has_execution_context": bool(execution_context),
            },
            context_refs={
                "candidate_profile_summary_id": candidate_profile_id,
                "conversation_summary_id": conversation_summary_id,
                "interview_plan_id": session.interview_plan_id,
                "execution_id": execution.id if execution else None,
                "answer_message_id": answer_message.id,
            },
            evidence_packet=evidence_packet,
            output_snapshot=lambda output: {"reply": output},
        )

    def memory(
        self,
        prompt_id: str,
        session,
        session_id: int,
        previous_content: str | None,
        profile_messages: list,
        previous_summary_id: int | None = None,
    ) -> AgentSpec:
        definition = self.agent_run_executor.definition(prompt_id)
        evidence_packet = self.evidence_builder.build_memory_packet(
            task=definition.task,
            session_id=session_id,
            project_id=session.project_id if session else None,
            messages=profile_messages,
        )
        return self.agent_run_executor.spec(
            prompt_id=prompt_id,
            project_id=session.project_id if session else None,
            session_id=session_id,
            input_snapshot={
                "summary_type": "candidate_profile" if prompt_id == "candidate_profile" else "conversation",
                "message_count": len(profile_messages or []),
                "from_round_no": profile_messages[0].round_no if profile_messages else None,
                "to_round_no": profile_messages[-1].round_no if profile_messages else None,
                "has_previous_content": bool(previous_content),
            },
            context_refs={
                "previous_summary_id": previous_summary_id,
                "message_ids": [message.id for message in profile_messages or []],
            },
            evidence_packet=evidence_packet,
            output_snapshot=lambda output: {"content": output},
        )

    def topic_judge(
        self,
        session,
        execution,
        current_section: dict,
        answer_message,
        recent_history: list,
    ) -> AgentSpec:
        evidence_packet = self.evidence_builder.build_topic_judge_packet(
            session_id=session.id,
            project_id=session.project_id,
            answer_message_id=answer_message.id,
            round_no=answer_message.round_no,
            user_answer=answer_message.content,
            current_section=current_section,
            execution_state=execution.state or {},
        )
        return self.agent_run_executor.spec(
            prompt_id="topic_completion_judge",
            project_id=session.project_id,
            session_id=session.id,
            input_snapshot={
                "round_no": answer_message.round_no,
                "answer_message_id": answer_message.id,
                "current_section_key": current_section.get("section_key"),
                "current_section_completed_rounds": current_section.get("completed_rounds"),
                "current_section_target_rounds": current_section.get("target_rounds"),
                "recent_history_count": len(recent_history or []),
            },
            context_refs={
                "interview_plan_id": session.interview_plan_id,
                "execution_id": execution.id,
                "answer_message_id": answer_message.id,
                "current_section_key": current_section.get("section_key"),
            },
            evidence_packet=evidence_packet,
        )
