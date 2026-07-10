from app.service.agent_run_service import AgentRunExecutor, AgentSpec
from app.service.agent_tools import ToolCall, ToolExecutionContext, ToolPlanningContext
from app.service.evidence_service import EvidencePacketBuilder


class InterviewAgentSpecBuilder:
    def __init__(
        self,
        agent_run_executor: AgentRunExecutor,
        evidence_builder: EvidencePacketBuilder,
        retriever=None,
        tool_runtime=None,
        tool_planner=None,
    ) -> None:
        self.agent_run_executor = agent_run_executor
        self.evidence_builder = evidence_builder
        self.retriever = retriever
        self.tool_runtime = tool_runtime
        self.tool_planner = tool_planner

    def evaluation(
        self,
        session,
        history: list,
        full_history: list,
        execution,
        candidate_profile,
        conversation_summary,
        workflow_run_id: str | None = None,
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
            workflow_context=self._workflow_context(
                workflow_id="post_interview_assessment",
                step_id="evaluation",
                session_id=session.id,
                workflow_run_id=workflow_run_id,
            ),
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
            workflow_context=self._workflow_context(
                workflow_id="interview_runtime",
                step_id="first_question",
                session_id=session.id,
            ),
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
        workflow_run_id: str | None = None,
    ) -> AgentSpec:
        prompt_id = "followup"
        definition = self.agent_run_executor.definition(prompt_id)
        tool_calls = self._plan_tools(
            task_name=definition.task,
            session=session,
            answer_message=answer_message,
            execution=execution,
        )
        tool_results = self._run_tools(
            session=session,
            answer_message=answer_message,
            tool_calls=tool_calls,
        )
        retrieved_knowledge = self._tool_outputs(tool_results)
        evidence_packet = self.evidence_builder.build_question_generation_packet(
            task=definition.task,
            session_id=session.id,
            project_id=session.project_id,
            user_answer_message_id=answer_message.id,
            user_answer=answer_message.content,
            round_no=answer_message.round_no,
            recent_history=recent_history,
            execution_state=execution.state if execution else None,
            retrieved_knowledge=retrieved_knowledge,
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
                "tool_calls": [item.to_dict() for item in tool_calls],
                "tool_results": self._tool_result_snapshots(tool_results),
                "retrieved_knowledge_count": len(retrieved_knowledge),
            },
            context_refs={
                "candidate_profile_summary_id": candidate_profile_id,
                "conversation_summary_id": conversation_summary_id,
                "interview_plan_id": session.interview_plan_id,
                "execution_id": execution.id if execution else None,
                "answer_message_id": answer_message.id,
                "tool_names": [item.tool_name for item in tool_calls],
            },
            evidence_packet=evidence_packet,
            workflow_context=self._workflow_context(
                workflow_id="interview_runtime",
                step_id="followup",
                session_id=session.id,
                workflow_run_id=workflow_run_id,
            ),
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
        workflow_run_id: str | None = None,
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
            workflow_context=self._workflow_context(
                workflow_id="interview_runtime",
                step_id="session_candidate_memory"
                if prompt_id == "candidate_profile"
                else "conversation_summary",
                session_id=session_id,
                workflow_run_id=workflow_run_id,
            ),
            output_snapshot=lambda output: {"content": output},
        )

    def topic_judge(
        self,
        session,
        execution,
        current_section: dict,
        answer_message,
        recent_history: list,
        workflow_run_id: str | None = None,
    ) -> AgentSpec:
        tool_calls = self._plan_tools(
            task_name="topic_completion_judge",
            session=session,
            answer_message=answer_message,
            current_section=current_section,
            execution=execution,
        )
        tool_results = self._run_tools(
            session=session,
            answer_message=answer_message,
            tool_calls=tool_calls,
        )
        retrieved_knowledge = self._tool_outputs(tool_results)
        evidence_packet = self.evidence_builder.build_topic_judge_packet(
            session_id=session.id,
            project_id=session.project_id,
            answer_message_id=answer_message.id,
            round_no=answer_message.round_no,
            user_answer=answer_message.content,
            current_section=current_section,
            execution_state=execution.state or {},
        )
        evidence_packet = self.evidence_builder.enrich_packet_with_retrieval(
            evidence_packet,
            project_id=session.project_id,
            session_id=session.id,
            retrieved_knowledge=retrieved_knowledge,
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
                "tool_calls": [item.to_dict() for item in tool_calls],
                "tool_results": self._tool_result_snapshots(tool_results),
                "retrieved_knowledge_count": len(retrieved_knowledge),
            },
            context_refs={
                "interview_plan_id": session.interview_plan_id,
                "execution_id": execution.id,
                "answer_message_id": answer_message.id,
                "current_section_key": current_section.get("section_key"),
                "tool_names": [item.tool_name for item in tool_calls],
            },
            evidence_packet=evidence_packet,
            workflow_context=self._workflow_context(
                workflow_id="interview_runtime",
                step_id="topic_completion_judge",
                session_id=session.id,
                workflow_run_id=workflow_run_id,
            ),
        )

    def _workflow_context(
        self,
        workflow_id: str,
        step_id: str,
        session_id: int | None = None,
        workflow_run_id: str | None = None,
    ) -> dict:
        return {
            "workflow_id": workflow_id,
            "workflow_run_id": workflow_run_id or self._workflow_run_id(
                workflow_id=workflow_id,
                session_id=session_id,
            ),
            "step_id": step_id,
        }

    def _workflow_run_id(
        self,
        workflow_id: str,
        session_id: int | None = None,
    ) -> str:
        if session_id is not None:
            return f"session_{session_id}_{workflow_id}"
        return workflow_id

    def _plan_tools(
        self,
        task_name: str,
        session,
        answer_message,
        current_section: dict | None = None,
        execution=None,
    ) -> list[ToolCall]:
        if self.tool_planner:
            return self.tool_planner.plan(
                ToolPlanningContext(
                    task_name=task_name,
                    session=session,
                    answer_message=answer_message,
                    current_section=current_section,
                    execution=execution,
                )
            )
        return self._fallback_tool_calls(task_name, session, answer_message)

    def _fallback_tool_calls(self, task_name: str, session, answer_message) -> list[ToolCall]:
        if task_name == "followup_generation":
            calls = [
                ToolCall(tool_name="get_previous_answer", query=answer_message.content),
            ]
            if session.project_id:
                calls.append(ToolCall(tool_name="get_resume_profile", query=""))
                calls.append(ToolCall(tool_name="search_technology", query=answer_message.content))
            return calls
        if task_name == "topic_completion_judge":
            calls = [
                ToolCall(tool_name="get_previous_answer", query=answer_message.content),
            ]
            if session.project_id:
                calls.append(ToolCall(tool_name="search_technology", query=answer_message.content))
            return calls
        return []

    def _run_tools(
        self,
        session,
        answer_message,
        tool_calls: list[ToolCall],
    ) -> list:
        if self.tool_runtime:
            return self.tool_runtime.execute(
                tool_calls,
                ToolExecutionContext(
                    session=session,
                    answer_message=answer_message,
                ),
            )
        if not self.retriever:
            return []
        results = []
        for call in tool_calls:
            tool_name = call.tool_name
            query = call.query or ""
            if tool_name == "get_resume_profile":
                results.extend(self.retriever.get_resume_profile(session.project_id))
            elif tool_name == "get_previous_answer":
                results.extend(
                    self.retriever.get_previous_answer(
                        session_id=session.id,
                        query=query,
                    )
                )
            elif tool_name == "search_company_info":
                results.extend(
                    self.retriever.search_company_info(
                        project_id=session.project_id,
                        query=query,
                    )
                )
            elif tool_name == "search_technology":
                results.extend(
                    self.retriever.search_technology(
                        project_id=session.project_id,
                        query=query,
                    )
                )
        return self._dedupe_results(results)

    def _tool_outputs(self, tool_results: list) -> list:
        if not tool_results:
            return []
        if all(hasattr(item, "outputs") for item in tool_results):
            outputs = []
            for result in tool_results:
                if getattr(result, "status", None) != "success":
                    continue
                outputs.extend(result.outputs)
            return self._dedupe_results(outputs)
        return self._dedupe_results(tool_results)

    def _tool_result_snapshots(self, tool_results: list) -> list[dict]:
        snapshots = []
        for item in tool_results:
            if hasattr(item, "to_snapshot"):
                snapshots.append(item.to_snapshot())
            else:
                snapshots.append(
                    {
                        "tool_name": (getattr(item, "metadata", {}) or {}).get("tool_name"),
                        "status": "success",
                        "output_count": 1,
                        "error_message": None,
                        "latency_ms": None,
                        "metadata": getattr(item, "metadata", {}) or {},
                    }
                )
        return snapshots

    def _dedupe_results(self, results: list) -> list:
        deduped = []
        seen = set()
        for item in results:
            key = (
                getattr(item, "source_type", None),
                getattr(item, "source_id", None),
                getattr(item, "source_name", None),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped
