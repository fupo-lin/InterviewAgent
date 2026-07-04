from __future__ import annotations

import logging
from typing import Any

from app.service.runtime_agents import (
    FollowupAgentInput,
    SessionMemoryAgentInput,
    TopicJudgeAgentInput,
)
from app.service.interview_runtime_state import InterviewRuntimeState, RuntimeContext


class InterviewRuntimeNodes:
    def __init__(
        self,
        *,
        message_repo,
        summary_repo,
        execution_repo,
        plan_repo,
        execution_service,
        topic_judge_agent,
        session_memory_agent,
        interview_executor_agent,
        agent_run_repo=None,
        logger_: logging.Logger | None = None,
    ) -> None:
        self.message_repo = message_repo
        self.summary_repo = summary_repo
        self.execution_repo = execution_repo
        self.plan_repo = plan_repo
        self.execution_service = execution_service
        self.agent_run_repo = agent_run_repo
        self.topic_judge_agent = topic_judge_agent
        self.session_memory_agent = session_memory_agent
        self.interview_executor_agent = interview_executor_agent
        self.logger = logger_ or logging.getLogger(__name__)

    def initial_chat_state(self, session, incoming_user_input: str) -> InterviewRuntimeState:
        return {
            "workflow_id": "interview_runtime",
            "thread_id": f"interview:{session.session_uid}",
            "status": "running",
            "project_id": session.project_id,
            "session_id": session.id,
            "session_uid": session.session_uid,
            "role_name": session.role_name,
            "interview_plan_id": session.interview_plan_id,
            "incoming_user_input": incoming_user_input,
            "completed_steps": [],
            "failed_steps": [],
            "last_memory_agent_run_ids": [],
            "last_error": None,
        }

    def save_user_answer_node(
        self,
        state: InterviewRuntimeState,
        session,
    ):
        round_no = self.message_repo.latest_assistant_question_round_no(session.id)
        existing = self._get_message_by_round(
            session_id=session.id,
            round_no=round_no,
            role_type="user",
            message_type="answer",
        )
        if existing:
            state["expected_user_round_no"] = round_no
            state["last_user_message_id"] = existing.id
            self._complete(state, "save_user_answer_reused")
            return existing

        answer_message = self.message_repo.create(
            session_id=session.id,
            role_type="user",
            message_type="answer",
            round_no=round_no,
            content=state.get("incoming_user_input") or "",
        )
        state["expected_user_round_no"] = round_no
        state["last_user_message_id"] = answer_message.id
        self._complete(state, "save_user_answer")
        return answer_message

    def load_runtime_context_node(
        self,
        state: InterviewRuntimeState,
        session,
    ) -> RuntimeContext:
        latest_completed_round_no = self.message_repo.latest_completed_round_no(session.id)
        recent_history = self.message_repo.list_recent_rounds(session.id, rounds=4)
        execution = self.execution_repo.get_active_by_session_id(session.id)
        candidate_profile = self.summary_repo.get_latest_by_session_id(
            session.id,
            "candidate_profile",
        )
        conversation_summary = self.summary_repo.get_latest_by_session_id(
            session.id,
            "conversation",
        )
        plan_context = self._session_plan_context(session)
        execution_context = self._session_execution_context(session, execution)
        self._sync_execution_state(state, execution)
        state["latest_candidate_memory_id"] = candidate_profile.id if candidate_profile else None
        state["latest_conversation_summary_id"] = (
            conversation_summary.id if conversation_summary else None
        )
        self._complete(state, "load_runtime_context")
        return RuntimeContext(
            latest_completed_round_no=latest_completed_round_no,
            recent_history=recent_history,
            execution=execution,
            candidate_profile=candidate_profile,
            conversation_summary=conversation_summary,
            plan_context=plan_context,
            execution_context=execution_context,
        )

    async def topic_judge_node(
        self,
        state: InterviewRuntimeState,
        session,
        answer_message,
        recent_history: list[Any],
        execution,
    ) -> dict | None:
        if not session.interview_plan_id or not execution:
            self._complete(state, "topic_judge_skipped")
            return None

        current_section = self.execution_service.current_section(execution)
        if not current_section:
            self._complete(state, "topic_judge_skipped")
            return None

        existing = self._get_agent_run_by_context(
            session_id=session.id,
            prompt_id="topic_completion_judge",
            context_refs={
                "answer_message_id": answer_message.id,
                "execution_id": execution.id,
            },
        )
        if existing:
            state["last_topic_judge_agent_run_id"] = existing.id
            state["last_agent_run_id"] = existing.id
            self._complete(state, "topic_judge_reused")
            return self._agent_run_output_payload(existing)

        try:
            run_result = await self.topic_judge_agent.run(
                TopicJudgeAgentInput(
                    session=session,
                    execution=execution,
                    current_section=current_section,
                    answer_message=answer_message,
                    recent_history=recent_history,
                    workflow_run_id=state.get("workflow_run_id"),
                )
            )
        except Exception as exc:
            self.logger.warning("Failed to judge topic completion", exc_info=True)
            self._fail_non_blocking(state, "topic_judge", exc)
            return None

        state["last_topic_judge_agent_run_id"] = run_result.agent_run.id
        state["last_agent_run_id"] = run_result.agent_run.id
        self._complete(state, "topic_judge")
        return {
            **(run_result.output or {}),
            "agent_run_id": run_result.agent_run.id,
            "schema_version": run_result.output_schema,
            "evidence_refs": run_result.evidence_refs,
        }

    def advance_execution_node(
        self,
        state: InterviewRuntimeState,
        execution,
        answer_message,
        judge_result: dict | None,
    ):
        if not execution:
            self._complete(state, "advance_execution_skipped")
            return None
        if self._execution_has_answer(execution, answer_message.id):
            self._sync_execution_state(state, execution)
            self._complete(state, "advance_execution_reused")
            return execution

        updated = self.execution_service.advance_after_answer(
            execution,
            answer_message.content,
            answer_message.round_no,
            judge_result,
        )
        if self._mark_execution_answer(updated, answer_message, judge_result):
            self.execution_repo.save(updated)
        self._sync_execution_state(state, updated)
        self._complete(state, "advance_execution")
        return updated

    async def refresh_memory_node(
        self,
        state: InterviewRuntimeState,
        session,
        latest_completed_round_no: int,
    ) -> None:
        if latest_completed_round_no < 10:
            self._complete(state, "refresh_memory_skipped")
            return

        latest_conversation = self.summary_repo.get_latest_by_session_id(
            session.id,
            "conversation",
        )
        latest_profile = self.summary_repo.get_latest_by_session_id(
            session.id,
            "candidate_profile",
        )
        profile_round = latest_profile.to_round_no if latest_profile else 0
        if not latest_profile or latest_completed_round_no - profile_round >= 10:
            profile_from_round_no = 1 if not latest_profile else latest_profile.to_round_no + 1
            profile_messages = self.message_repo.list_between_rounds(
                session.id,
                profile_from_round_no,
                latest_completed_round_no,
            )
            if profile_messages:
                existing = self._get_summary_by_range(
                    session_id=session.id,
                    summary_type="candidate_profile",
                    from_round_no=1,
                    to_round_no=latest_completed_round_no,
                )
                if existing:
                    state["latest_candidate_memory_id"] = existing.id
                    self._remember_agent_run(state, existing.agent_run_id)
                else:
                    try:
                        summary_fields = await self._generate_memory_with_run(
                            prompt_id="candidate_profile",
                            session=session,
                            previous_content=latest_profile.content if latest_profile else None,
                            profile_messages=profile_messages,
                            previous_summary_id=latest_profile.id if latest_profile else None,
                            workflow_run_id=state.get("workflow_run_id"),
                        )
                    except Exception as exc:
                        self.logger.warning(
                            "Failed to refresh candidate profile summary",
                            exc_info=True,
                        )
                        self._fail_non_blocking(state, "candidate_profile_memory", exc)
                    else:
                        summary = self.summary_repo.create(
                            session_id=session.id,
                            summary_type="candidate_profile",
                            from_round_no=1,
                            to_round_no=latest_completed_round_no,
                            **summary_fields,
                        )
                        state["latest_candidate_memory_id"] = summary.id
                        self._remember_agent_run(state, summary.agent_run_id)

        last_summary_round = latest_conversation.to_round_no if latest_conversation else 0
        if latest_conversation and latest_completed_round_no - last_summary_round < 5:
            self._complete(state, "refresh_memory")
            return

        from_round_no = 1 if not latest_conversation else latest_conversation.to_round_no + 1
        new_messages = self.message_repo.list_between_rounds(
            session.id,
            from_round_no,
            latest_completed_round_no,
        )
        if not new_messages:
            self._complete(state, "refresh_memory")
            return

        existing = self._get_summary_by_range(
            session_id=session.id,
            summary_type="conversation",
            from_round_no=1,
            to_round_no=latest_completed_round_no,
        )
        if existing:
            state["latest_conversation_summary_id"] = existing.id
            self._remember_agent_run(state, existing.agent_run_id)
            self._complete(state, "refresh_memory")
            return

        try:
            summary_fields = await self._generate_memory_with_run(
                prompt_id="conversation_summary",
                session=session,
                previous_content=latest_conversation.content if latest_conversation else None,
                profile_messages=new_messages,
                previous_summary_id=latest_conversation.id if latest_conversation else None,
                workflow_run_id=state.get("workflow_run_id"),
            )
        except Exception as exc:
            self.logger.warning("Failed to refresh conversation summary", exc_info=True)
            self._fail_non_blocking(state, "conversation_summary_memory", exc)
        else:
            summary = self.summary_repo.create(
                session_id=session.id,
                summary_type="conversation",
                from_round_no=1,
                to_round_no=latest_completed_round_no,
                **summary_fields,
            )
            state["latest_conversation_summary_id"] = summary.id
            self._remember_agent_run(state, summary.agent_run_id)

        self._complete(state, "refresh_memory")

    def reload_followup_context_node(
        self,
        state: InterviewRuntimeState,
        session,
        execution,
    ) -> RuntimeContext:
        latest_completed_round_no = self.message_repo.latest_completed_round_no(session.id)
        recent_history = self.message_repo.list_recent_rounds(session.id, rounds=4)
        candidate_profile = self.summary_repo.get_latest_by_session_id(
            session.id,
            "candidate_profile",
        )
        conversation_summary = self.summary_repo.get_latest_by_session_id(
            session.id,
            "conversation",
        )
        plan_context = self._session_plan_context(session)
        execution_context = self._session_execution_context(session, execution)
        state["latest_candidate_memory_id"] = candidate_profile.id if candidate_profile else None
        state["latest_conversation_summary_id"] = (
            conversation_summary.id if conversation_summary else None
        )
        self._complete(state, "reload_followup_context")
        return RuntimeContext(
            latest_completed_round_no=latest_completed_round_no,
            recent_history=recent_history,
            execution=execution,
            candidate_profile=candidate_profile,
            conversation_summary=conversation_summary,
            plan_context=plan_context,
            execution_context=execution_context,
        )

    async def generate_followup_node(
        self,
        state: InterviewRuntimeState,
        session,
        answer_message,
        context: RuntimeContext,
    ):
        existing = self._get_agent_run_by_context(
            session_id=session.id,
            prompt_id="followup",
            context_refs={"answer_message_id": answer_message.id},
        )
        if existing:
            state["last_followup_agent_run_id"] = existing.id
            state["last_agent_run_id"] = existing.id
            self._complete(state, "generate_followup_reused")
            return self._agent_run_message_fields(existing)

        run_result = await self.interview_executor_agent.run(
            FollowupAgentInput(
                session=session,
                answer_message=answer_message,
                recent_history=context.recent_history,
                candidate_profile=(
                    context.candidate_profile.content if context.candidate_profile else None
                ),
                conversation_summary=(
                    context.conversation_summary.content
                    if context.conversation_summary
                    else None
                ),
                plan_context=context.plan_context,
                execution_context=context.execution_context,
                candidate_profile_id=(
                    context.candidate_profile.id if context.candidate_profile else None
                ),
                conversation_summary_id=(
                    context.conversation_summary.id
                    if context.conversation_summary
                    else None
                ),
                execution=context.execution,
                workflow_run_id=state.get("workflow_run_id"),
            )
        )
        state["last_followup_agent_run_id"] = run_result.agent_run.id
        state["last_agent_run_id"] = run_result.agent_run.id
        self._complete(state, "generate_followup")
        return run_result.message_fields()

    def save_assistant_message_node(
        self,
        state: InterviewRuntimeState,
        session,
        round_no: int,
        message_fields: dict,
        execution,
    ):
        existing = self._get_message_by_round(
            session_id=session.id,
            round_no=round_no,
            role_type="assistant",
        )
        if existing:
            state["last_assistant_message_id"] = existing.id
            state["status"] = "waiting_user"
            self._complete(state, "save_assistant_message_reused")
            return existing

        message = self.message_repo.create(
            session_id=session.id,
            role_type="assistant",
            message_type="followup",
            round_no=round_no,
            **{
                **message_fields,
                "raw_response": {
                    **(message_fields.get("raw_response") or {}),
                    "execution": self.execution_service.response(execution)
                    if execution
                    else None,
                },
            },
        )
        state["last_assistant_message_id"] = message.id
        state["status"] = "waiting_user"
        self._complete(state, "save_assistant_message")
        return message

    def _get_agent_run_by_context(
        self,
        session_id: int,
        prompt_id: str,
        context_refs: dict,
    ):
        if not self.agent_run_repo:
            return None
        getter = getattr(self.agent_run_repo, "get_latest_success_by_context", None)
        if not getter:
            return None
        return getter(
            session_id=session_id,
            prompt_id=prompt_id,
            context_refs=context_refs,
        )

    def _agent_run_output_payload(self, agent_run) -> dict:
        output = agent_run.output_snapshot or {}
        payload = output.get("result") if isinstance(output, dict) else None
        if not isinstance(payload, dict):
            payload = output if isinstance(output, dict) else {}
        return {
            **payload,
            "agent_run_id": agent_run.id,
            "schema_version": agent_run.output_schema_version,
            "evidence_refs": agent_run.evidence_refs or [],
        }

    def _agent_run_message_fields(self, agent_run) -> dict:
        output = agent_run.output_snapshot or {}
        content = output.get("result") if isinstance(output, dict) else None
        if content is None and isinstance(output, dict):
            content = output.get("content") or output.get("reply")
        if content is None:
            content = ""
        return {
            "content": content,
            "raw_response": agent_run.raw_response,
            "agent_run_id": agent_run.id,
            "schema_version": agent_run.output_schema_version,
            "evidence_refs": agent_run.evidence_refs or [],
        }

    def _get_message_by_round(
        self,
        session_id: int,
        round_no: int,
        role_type: str,
        message_type: str | None = None,
    ):
        getter = getattr(self.message_repo, "get_by_round", None)
        if not getter:
            return None
        return getter(
            session_id=session_id,
            round_no=round_no,
            role_type=role_type,
            message_type=message_type,
        )

    def _get_summary_by_range(
        self,
        session_id: int,
        summary_type: str,
        from_round_no: int,
        to_round_no: int,
    ):
        getter = getattr(self.summary_repo, "get_by_range", None)
        if not getter:
            return None
        return getter(
            session_id=session_id,
            summary_type=summary_type,
            from_round_no=from_round_no,
            to_round_no=to_round_no,
        )

    def _execution_has_answer(self, execution, answer_message_id: int | None) -> bool:
        if not answer_message_id:
            return False
        for section in (execution.state or {}).get("sections") or []:
            for item in section.get("evidence") or []:
                if item.get("answer_message_id") == answer_message_id:
                    return True
        return False

    def _mark_execution_answer(
        self,
        execution,
        answer_message,
        judge_result: dict | None,
    ) -> bool:
        if not execution or not answer_message:
            return False
        state = execution.state or {}
        for section in state.get("sections") or []:
            evidence_items = section.get("evidence") or []
            for item in reversed(evidence_items):
                if item.get("round_no") == answer_message.round_no and not item.get(
                    "answer_message_id"
                ):
                    item["answer_message_id"] = answer_message.id
                    if judge_result and judge_result.get("agent_run_id"):
                        item["topic_judge_agent_run_id"] = judge_result.get("agent_run_id")
                    return True
        return False

    async def _generate_memory_with_run(
        self,
        prompt_id: str,
        session,
        previous_content: str | None,
        profile_messages: list,
        previous_summary_id: int | None = None,
        workflow_run_id: str | None = None,
    ) -> dict:
        run_result = await self.session_memory_agent.run(
            SessionMemoryAgentInput(
                prompt_id=prompt_id,
                session=session,
                session_id=session.id,
                previous_content=previous_content,
                profile_messages=profile_messages,
                previous_summary_id=previous_summary_id,
                workflow_run_id=workflow_run_id,
            )
        )
        return run_result.message_fields()

    def _session_plan_context(self, session) -> str | None:
        if not session.interview_plan_id:
            return None
        plan = self.plan_repo.get_by_id(session.interview_plan_id)
        return self._plan_context(plan) if plan else None

    def _session_execution_context(self, session, execution=None) -> str | None:
        if not session.interview_plan_id:
            return None
        plan = self.plan_repo.get_by_id(session.interview_plan_id)
        execution = execution or self.execution_repo.get_latest_by_session_id(session.id)
        return self.execution_service.context_for_followup(
            execution,
            plan.content if plan else None,
        )

    def _plan_context(self, plan) -> str:
        content = plan.content or {}
        return (
            f"InterviewPlan mode: {plan.plan_mode}\n"
            f"Role: {content.get('role_name') or content.get('roleName') or ''}\n"
            f"Sections: {content.get('sections', [])}\n"
            f"Evaluation rubric: {content.get('evaluation_rubric') or content.get('evaluationRubric') or []}"
        )

    def _sync_execution_state(
        self,
        state: InterviewRuntimeState,
        execution,
    ) -> None:
        if not execution:
            return
        next_action = (execution.state or {}).get("next_action") or {}
        state["execution_id"] = execution.id
        state["current_section_key"] = execution.current_section_key
        state["current_section_index"] = execution.current_section_index
        state["current_section_round_no"] = execution.current_section_round_no
        state["total_completed_round_no"] = execution.total_completed_round_no
        state["next_action"] = next_action.get("type")

    def _complete(self, state: InterviewRuntimeState, step_id: str) -> None:
        completed = state.setdefault("completed_steps", [])
        if step_id not in completed:
            completed.append(step_id)

    def _fail_non_blocking(
        self,
        state: InterviewRuntimeState,
        step_id: str,
        exc: Exception,
    ) -> None:
        failed = state.setdefault("failed_steps", [])
        if step_id not in failed:
            failed.append(step_id)
        state["last_error"] = {
            "step_id": step_id,
            "message": str(exc),
        }

    def _remember_agent_run(
        self,
        state: InterviewRuntimeState,
        agent_run_id: int | None,
    ) -> None:
        if not agent_run_id:
            return
        runs = state.setdefault("last_memory_agent_run_ids", [])
        runs.append(agent_run_id)
