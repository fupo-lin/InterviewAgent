from __future__ import annotations

import logging
from inspect import Parameter, signature
from typing import Any

from app.service.runtime_agents import (
    FollowupAgentInput,
    SessionMemoryAgentInput,
    TopicJudgeAgentInput,
)
from app.service.interview_memory_contract import (
    ensure_runtime_memory_item_shape,
    is_actionable_memory_item,
    memory_identity,
    normalize_runtime_memory_item,
)
from app.service.interview_runtime_state import InterviewRuntimeState, RuntimeContext


MEMORY_REFRESH_ROUND_INTERVAL = 15
RECENT_HISTORY_ROUNDS = 4


class InterviewRuntimeNodes:
    def __init__(
        self,
        *,
        message_repo,
        summary_repo,
        execution_repo,
        session_repo=None,
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
        self.session_repo = session_repo
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
            "active_step": None,
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
            "runtime_decision": None,
            "open_threads": [],
            "memory_refs": {},
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
        return self.build_runtime_context(
            state,
            session=session,
            completed_step_id="load_runtime_context",
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
            payload = self._agent_run_output_payload(existing)
            self._close_answered_open_threads(
                state=state,
                answer_message=answer_message,
                judge_result=payload,
            )
            self._merge_open_threads(
                state=state,
                judge_result=payload,
                answer_message=answer_message,
                current_section=current_section,
            )
            self._persist_business_state_to_execution(state, execution)
            return payload

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
        payload = {
            **(run_result.output or {}),
            "agent_run_id": run_result.agent_run.id,
            "schema_version": run_result.output_schema,
            "evidence_refs": run_result.evidence_refs,
        }
        self._close_answered_open_threads(
            state=state,
            answer_message=answer_message,
            judge_result=payload,
        )
        self._merge_open_threads(
            state=state,
            judge_result=payload,
            answer_message=answer_message,
            current_section=current_section,
        )
        self._persist_business_state_to_execution(state, execution)
        return payload

    def advance_execution_node(
        self,
        state: InterviewRuntimeState,
        execution,
        answer_message,
        judge_result: dict | None,
        recent_history: list[Any] | None = None,
        retrieved_evidence=None,
    ):
        if not execution:
            self._complete(state, "advance_execution_skipped")
            return None
        if self._execution_has_answer(execution, answer_message.id):
            self._persist_business_state_to_execution(state, execution)
            self._sync_execution_state(state, execution)
            self._complete(state, "advance_execution_reused")
            return execution

        self._apply_business_state_to_execution(state, execution)
        updated = self._advance_after_answer(
            execution,
            answer_message.content,
            answer_message.round_no,
            judge_result,
            open_threads=state.get("open_threads", []),
            recent_history=recent_history,
            retrieved_evidence=retrieved_evidence,
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
        if latest_completed_round_no < MEMORY_REFRESH_ROUND_INTERVAL:
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
        if not latest_profile or latest_completed_round_no - profile_round >= MEMORY_REFRESH_ROUND_INTERVAL:
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
        if latest_conversation and latest_completed_round_no - last_summary_round < MEMORY_REFRESH_ROUND_INTERVAL:
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
        return self.build_runtime_context(
            state,
            session=session,
            execution=execution,
            completed_step_id="reload_followup_context",
        )

    def build_runtime_context(
        self,
        state: InterviewRuntimeState,
        *,
        session,
        execution=None,
        completed_step_id: str,
    ) -> RuntimeContext:
        latest_completed_round_no = self.message_repo.latest_completed_round_no(session.id)
        recent_history = self.message_repo.list_recent_rounds(session.id, rounds=RECENT_HISTORY_ROUNDS)
        execution = execution or self.execution_repo.get_active_by_session_id(session.id)
        candidate_profile = self.summary_repo.get_latest_by_session_id(
            session.id,
            "candidate_profile",
        )
        conversation_summary = self.summary_repo.get_latest_by_session_id(
            session.id,
            "conversation",
        )
        plan_context = self._session_plan_context(session)
        self._sync_execution_state(state, execution)
        execution_context = self._append_open_threads_context(
            self._session_execution_context(session, execution),
            state.get("open_threads", []),
        )
        state["latest_candidate_memory_id"] = candidate_profile.id if candidate_profile else None
        state["latest_conversation_summary_id"] = (
            conversation_summary.id if conversation_summary else None
        )
        self._sync_memory_refs(
            state,
            recent_history=recent_history,
            execution=execution,
            candidate_profile=candidate_profile,
            conversation_summary=conversation_summary,
        )
        self._apply_business_state_to_execution(state, execution)
        self._complete(state, completed_step_id)
        return RuntimeContext(
            latest_completed_round_no=latest_completed_round_no,
            recent_history=recent_history,
            execution=execution,
            candidate_profile=candidate_profile,
            conversation_summary=conversation_summary,
            plan_context=plan_context,
            execution_context=execution_context,
            open_threads=state.get("open_threads", []),
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
                open_threads=context.open_threads,
            )
        )
        state["last_followup_agent_run_id"] = run_result.agent_run.id
        state["last_agent_run_id"] = run_result.agent_run.id
        self._remember_memory_ref_agent_run(state, run_result.agent_run.id)
        self._select_open_threads_for_followup(
            state,
            agent_run_id=run_result.agent_run.id,
            step_id="generate_followup",
        )
        self._persist_business_state_to_execution(state, context.execution)
        self._complete(state, "generate_followup")
        return run_result.message_fields()

    async def generate_wrap_up_question_node(
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
            self._complete(state, "generate_wrap_up_question_reused")
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
                open_threads=context.open_threads,
            )
        )
        state["last_followup_agent_run_id"] = run_result.agent_run.id
        state["last_agent_run_id"] = run_result.agent_run.id
        self._remember_memory_ref_agent_run(state, run_result.agent_run.id)
        self._select_open_threads_for_followup(
            state,
            agent_run_id=run_result.agent_run.id,
            step_id="generate_wrap_up_question",
        )
        self._persist_business_state_to_execution(state, context.execution)
        self._complete(state, "generate_wrap_up_question")
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
            self._mark_selected_threads_asked(state, existing)
            self._persist_business_state_to_execution(state, execution)
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
        self._mark_selected_threads_asked(state, message)
        self._persist_business_state_to_execution(state, execution)
        self._complete(state, "save_assistant_message")
        return message

    def save_wrap_up_message_node(
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
            message_type="wrap_up",
        )
        if existing:
            state["last_assistant_message_id"] = existing.id
            state["status"] = "waiting_user"
            self._mark_selected_threads_asked(state, existing)
            self._persist_business_state_to_execution(state, execution)
            self._complete(state, "save_wrap_up_message_reused")
            return existing

        message = self.message_repo.create(
            session_id=session.id,
            role_type="assistant",
            message_type="wrap_up",
            round_no=round_no,
            **{
                **message_fields,
                "raw_response": {
                    **(message_fields.get("raw_response") or {}),
                    "source": "interview_runtime_wrap_up",
                    "route_after_advance": state.get("route_after_advance"),
                    "route_after_advance_reason": state.get("route_after_advance_reason"),
                    "execution": self.execution_service.response(execution)
                    if execution
                    else None,
                },
            },
        )
        state["last_assistant_message_id"] = message.id
        state["status"] = "waiting_user"
        self._mark_selected_threads_asked(state, message)
        self._persist_business_state_to_execution(state, execution)
        self._complete(state, "save_wrap_up_message")
        return message

    def finalize_interview_node(
        self,
        state: InterviewRuntimeState,
        session,
        answer_message,
        execution,
    ):
        round_no = answer_message.round_no + 1
        existing = self._get_message_by_round(
            session_id=session.id,
            round_no=round_no,
            role_type="assistant",
            message_type="summary",
        )
        if existing:
            message = existing
            self._complete(state, "finalize_interview_reused")
        else:
            message = self.message_repo.create(
                session_id=session.id,
                role_type="assistant",
                message_type="summary",
                round_no=round_no,
                content=self._final_message(),
                raw_response={
                    "source": "interview_runtime_finalize",
                    "route_after_advance": state.get("route_after_advance"),
                    "route_after_advance_reason": state.get("route_after_advance_reason"),
                    "execution": self.execution_service.response(execution)
                    if execution
                    else None,
                },
                agent_run_id=None,
                schema_version=None,
                evidence_refs=[],
            )
            self._complete(state, "finalize_interview")

        if execution:
            execution.status = "finished"
            execution_state = execution.state or {}
            execution_state["next_action"] = {
                "type": "finished",
                "reason": "interview_runtime_finalized",
            }
            execution.state = execution_state
            self.execution_repo.save(execution)
            self._sync_execution_state(state, execution)

        if self.session_repo:
            marker = getattr(self.session_repo, "mark_finished", None)
            if marker:
                marker(session)
        else:
            session.status = "finished"

        state["last_assistant_message_id"] = message.id
        state["status"] = "finished"
        state["active_step"] = None
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

    def _advance_after_answer(
        self,
        execution,
        answer: str,
        round_no: int,
        judge_result: dict | None,
        **kwargs,
    ):
        advance = self.execution_service.advance_after_answer
        try:
            parameters = signature(advance).parameters
        except (TypeError, ValueError):
            parameters = {}
        accepts_kwargs = any(
            parameter.kind == Parameter.VAR_KEYWORD
            for parameter in parameters.values()
        )
        supported_kwargs = {
            key: value
            for key, value in kwargs.items()
            if accepts_kwargs or key in parameters
        }
        return advance(
            execution,
            answer,
            round_no,
            judge_result,
            **supported_kwargs,
        )

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

    def _append_open_threads_context(
        self,
        execution_context: str | None,
        open_threads: list[dict] | None,
    ) -> str | None:
        active_threads = [
            item for item in open_threads or [] if item.get("status") == "open"
        ]
        if not active_threads:
            return execution_context
        lines = [execution_context or "InterviewPlanExecution:", "OpenFollowupThreads:"]
        for item in active_threads[:5]:
            lines.append(
                "- "
                f"round={item.get('round_no')}; "
                f"probe_point={item.get('probe_point') or ''}; "
                f"highlight={item.get('highlight') or ''}; "
                f"missing_detail={item.get('missing_detail') or ''}"
            )
        return "\n".join(lines)

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
        execution_state = execution.state or {}
        next_action = execution_state.get("next_action") or {}
        state["execution_id"] = execution.id
        state["current_section_key"] = execution.current_section_key
        state["current_section_index"] = execution.current_section_index
        state["current_section_round_no"] = execution.current_section_round_no
        state["total_completed_round_no"] = execution.total_completed_round_no
        state["next_action"] = next_action.get("type")
        self._sync_business_state_from_execution(state, execution)

    def _sync_business_state_from_execution(
        self,
        state: InterviewRuntimeState,
        execution,
    ) -> None:
        execution_state = execution.state or {}
        execution_threads = execution_state.get("open_threads")
        if isinstance(execution_threads, list) and execution_threads:
            state["open_threads"] = self._runtime_memory_items(execution_threads)
        elif "open_threads" not in state:
            state["open_threads"] = []

        execution_memory_refs = execution_state.get("memory_refs")
        if isinstance(execution_memory_refs, dict) and execution_memory_refs:
            state["memory_refs"] = dict(execution_memory_refs)
        elif "memory_refs" not in state:
            state["memory_refs"] = {}

    def _apply_business_state_to_execution(
        self,
        state: InterviewRuntimeState,
        execution,
    ) -> bool:
        if not execution:
            return False
        execution_state = dict(execution.state or {})
        changed = False

        open_threads = state.get("open_threads")
        shaped_open_threads = self._runtime_memory_items(open_threads or [])
        if execution_state.get("open_threads") != shaped_open_threads:
            execution_state["open_threads"] = shaped_open_threads
            state["open_threads"] = shaped_open_threads
            changed = True

        memory_refs = state.get("memory_refs")
        if isinstance(memory_refs, dict) and execution_state.get("memory_refs") != memory_refs:
            execution_state["memory_refs"] = dict(memory_refs)
            changed = True

        if changed:
            execution.state = execution_state
        return changed

    def _persist_business_state_to_execution(
        self,
        state: InterviewRuntimeState,
        execution,
    ) -> None:
        if self._apply_business_state_to_execution(state, execution):
            self.execution_repo.save(execution)

    def _runtime_memory_items(self, items: list) -> list[dict]:
        shaped = []
        for item in items or []:
            normalized = ensure_runtime_memory_item_shape(item)
            if normalized:
                shaped.append(normalized)
        return shaped

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

    def _remember_memory_ref_agent_run(
        self,
        state: InterviewRuntimeState,
        agent_run_id: int | None,
    ) -> None:
        if not agent_run_id:
            return
        refs = dict(state.get("memory_refs") or {})
        runs = list(refs.get("agent_run_ids") or [])
        if agent_run_id not in runs:
            runs.append(agent_run_id)
        refs["agent_run_ids"] = runs
        state["memory_refs"] = refs

    def _sync_memory_refs(
        self,
        state: InterviewRuntimeState,
        *,
        recent_history: list,
        execution,
        candidate_profile,
        conversation_summary,
    ) -> None:
        refs = dict(state.get("memory_refs") or {})
        refs.update(
            {
                "recent_message_ids": [
                    item.id for item in recent_history or [] if getattr(item, "id", None)
                ],
                "candidate_profile_summary_id": candidate_profile.id
                if candidate_profile
                else None,
                "conversation_summary_id": conversation_summary.id
                if conversation_summary
                else None,
                "execution_id": execution.id if execution else None,
                "agent_run_ids": [
                    item
                    for item in [
                        state.get("last_topic_judge_agent_run_id"),
                        state.get("last_followup_agent_run_id"),
                        *(state.get("last_memory_agent_run_ids") or []),
                    ]
                    if item
                ],
            }
        )
        state["memory_refs"] = refs

    def _select_open_threads_for_followup(
        self,
        state: InterviewRuntimeState,
        *,
        agent_run_id: int | None,
        step_id: str,
    ) -> None:
        if not agent_run_id:
            return
        threads = list(state.get("open_threads") or [])
        selected = False
        for item in self._prioritized_threads(threads):
            if item.get("status") != "open":
                continue
            item["status"] = "selected"
            item["selected_agent_run_id"] = agent_run_id
            item["selected_step_id"] = step_id
            selected = True
            break
        if selected:
            state["open_threads"] = threads

    def _mark_selected_threads_asked(
        self,
        state: InterviewRuntimeState,
        assistant_message,
    ) -> None:
        threads = list(state.get("open_threads") or [])
        changed = False
        for item in threads:
            if not isinstance(item, dict) or item.get("status") != "selected":
                continue
            item["status"] = "asked"
            item["asked_message_id"] = getattr(assistant_message, "id", None)
            item["asked_round_no"] = getattr(assistant_message, "round_no", None)
            changed = True
        if changed:
            state["open_threads"] = threads

    def _close_answered_open_threads(
        self,
        *,
        state: InterviewRuntimeState,
        answer_message,
        judge_result: dict | None,
    ) -> None:
        threads = list(state.get("open_threads") or [])
        if not threads:
            return
        judge = judge_result or {}
        covered = {str(item) for item in judge.get("covered_probe_points") or []}
        answer_quality = str(judge.get("answer_quality") or "").lower()
        changed = False
        for item in threads:
            if not isinstance(item, dict) or item.get("status") != "asked":
                continue
            asked_round_no = item.get("asked_round_no")
            if asked_round_no != getattr(answer_message, "round_no", None):
                continue
            probe_point = str(item.get("probe_point") or "")
            if probe_point and covered and probe_point not in covered:
                continue
            if answer_quality == "low":
                item["status"] = "open"
                item["reopened_reason"] = "candidate_answer_quality_low"
            else:
                item["status"] = "closed"
                item["answered_message_id"] = getattr(answer_message, "id", None)
                item["closed_reason"] = "candidate_answer_received"
                item["closed_by_topic_judge_agent_run_id"] = judge.get("agent_run_id")
            changed = True
        if changed:
            state["open_threads"] = threads

    def _prioritized_threads(self, threads: list[dict]) -> list[dict]:
        priority_order = {"high": 0, "medium": 1, "low": 2}
        return sorted(
            [item for item in threads if isinstance(item, dict)],
            key=lambda item: (
                priority_order.get(str(item.get("priority") or "medium"), 1),
                item.get("round_no") or 0,
            ),
        )

    def _merge_open_threads(
        self,
        *,
        state: InterviewRuntimeState,
        judge_result: dict | None,
        answer_message,
        current_section: dict | None,
    ) -> None:
        if not judge_result:
            return
        section = current_section or {}
        incoming = []
        incoming.extend(
            self._runtime_memory_items_from_judge(
                judge_result=judge_result,
                answer_message=answer_message,
                current_section=section,
            )
        )
        if not incoming:
            return

        existing = list(state.get("open_threads") or [])
        seen = {memory_identity(item) for item in existing if isinstance(item, dict)}
        for thread in incoming:
            if not is_actionable_memory_item(thread):
                continue
            key = memory_identity(thread)
            if key in seen:
                continue
            seen.add(key)
            existing.append(thread)
        state["open_threads"] = existing

    def _runtime_memory_items_from_judge(
        self,
        *,
        judge_result: dict,
        answer_message,
        current_section: dict,
    ) -> list[dict]:
        field_specs = (
            ("open_threads", "open_followup"),
            ("technical_highlights", "technical_highlight"),
            ("project_claims", "project_claim"),
            ("missing_details", "missing_detail"),
            ("risk_signals", "risk_signal"),
        )
        items: list[dict] = []
        agent_run_id = judge_result.get("agent_run_id")
        for field_name, memory_type in field_specs:
            raw_items = judge_result.get(field_name) or []
            if not isinstance(raw_items, list):
                continue
            for index, item in enumerate(raw_items, start=1):
                items.append(
                    normalize_runtime_memory_item(
                        item=item,
                        memory_type=memory_type,
                        index=index,
                        answer_message=answer_message,
                        current_section=current_section,
                        source_field=field_name,
                        agent_run_id=agent_run_id,
                    )
                )
        return items

    def _final_message(self) -> str:
        return (
            "本次模拟面试已经完成。接下来我会基于你的回答生成评估结果，"
            "你也可以查看面试记录并继续完善项目和简历材料。"
        )
