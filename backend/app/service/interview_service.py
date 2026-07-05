import logging
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.repository.interview_repository import (
    InterviewEvaluationRepository,
    InterviewMessageRepository,
    InterviewPlanExecutionRepository,
    InterviewSessionRepository,
    InterviewSummaryRepository,
)
from app.repository.agent_run_repository import AgentRunRepository
from app.repository.workflow_run_repository import WorkflowRunRepository
from app.repository.preparation_repository import InterviewPlanRepository, PreparationProjectRepository
from app.service.agent_run_service import AgentRunExecutor, AgentRunRecorder
from app.service.agent_runtime import AgentRuntimeConfig
from app.service.assessment_agents import EvaluationAgent
from app.service.evidence_service import EvidencePacketBuilder
from app.service.interview_agent_spec_builder import InterviewAgentSpecBuilder
from app.service.interview_execution_service import InterviewExecutionService
from app.service.interview_runtime_nodes import InterviewRuntimeNodes
from app.service.interview_runtime_workflow import InterviewRuntimeWorkflow
from app.service.post_interview_assessment_nodes import PostInterviewAssessmentNodes
from app.service.post_interview_assessment_workflow import PostInterviewAssessmentWorkflow
from app.service.preparation_service import PreparationService
from app.service.workflow_runtime import WorkflowRuntime
from app.service.runtime_agents import (
    FirstQuestionAgentInput,
    FollowupAgentInput,
    InterviewExecutorAgent,
    SessionMemoryAgent,
    SessionMemoryAgentInput,
    TopicJudgeAgent,
    TopicJudgeAgentInput,
)
from app.schemas.interview import DeleteResponse, EvaluationResponse, HistoryResponse, MessageResponse
from app.service.llm_service import LLMService


logger = logging.getLogger(__name__)


class InterviewService:
    def __init__(self, db: Session):
        self.db = db
        self.session_repo = InterviewSessionRepository(db)
        self.message_repo = InterviewMessageRepository(db)
        self.evaluation_repo = InterviewEvaluationRepository(db)
        self.summary_repo = InterviewSummaryRepository(db)
        self.execution_repo = InterviewPlanExecutionRepository(db)
        self.agent_run_repo = AgentRunRepository(db)
        self.workflow_run_repo = WorkflowRunRepository(db)
        self.execution_service = InterviewExecutionService(self.execution_repo)
        self.project_repo = PreparationProjectRepository(db)
        self.plan_repo = InterviewPlanRepository(db)
        self.llm = LLMService()
        self.evidence_builder = EvidencePacketBuilder()
        self.agent_run_recorder = AgentRunRecorder(db)
        self.agent_run_executor = AgentRunExecutor(db, self.agent_run_recorder)
        self.interview_agent_spec_builder = InterviewAgentSpecBuilder(
            agent_run_executor=self.agent_run_executor,
            evidence_builder=self.evidence_builder,
        )
        self.evaluation_agent = EvaluationAgent(
            agent_run_executor=self.agent_run_executor,
            evidence_builder=self.evidence_builder,
            llm=self.llm,
            config=AgentRuntimeConfig(model_name=self.llm.model),
        )
        self.session_memory_agent = SessionMemoryAgent(
            agent_run_executor=self.agent_run_executor,
            evidence_builder=self.evidence_builder,
            llm=self.llm,
            config=AgentRuntimeConfig(model_name=self.llm.model),
        )
        self.topic_judge_agent = TopicJudgeAgent(
            agent_run_executor=self.agent_run_executor,
            evidence_builder=self.evidence_builder,
            llm=self.llm,
            config=AgentRuntimeConfig(model_name=self.llm.model),
        )
        self.interview_executor_agent = InterviewExecutorAgent(
            agent_run_executor=self.agent_run_executor,
            evidence_builder=self.evidence_builder,
            llm=self.llm,
            config=AgentRuntimeConfig(model_name=self.llm.model),
        )
        self.runtime_nodes = InterviewRuntimeNodes(
            message_repo=self.message_repo,
            summary_repo=self.summary_repo,
            execution_repo=self.execution_repo,
            plan_repo=self.plan_repo,
            execution_service=self.execution_service,
            topic_judge_agent=self.topic_judge_agent,
            session_memory_agent=self.session_memory_agent,
            interview_executor_agent=self.interview_executor_agent,
            agent_run_repo=self.agent_run_repo,
            logger_=logger,
        )
        self.workflow_runtime = WorkflowRuntime(self.workflow_run_repo)
        self.runtime_workflow = InterviewRuntimeWorkflow(
            self.runtime_nodes,
            runtime=self.workflow_runtime,
        )
        self.assessment_nodes = PostInterviewAssessmentNodes(
            message_repo=self.message_repo,
            evaluation_repo=self.evaluation_repo,
            summary_repo=self.summary_repo,
            execution_repo=self.execution_repo,
            plan_repo=self.plan_repo,
            session_repo=self.session_repo,
            execution_service=self.execution_service,
            evaluation_agent=self.evaluation_agent,
        )
        self.assessment_workflow = PostInterviewAssessmentWorkflow(
            self.assessment_nodes,
            runtime=self.workflow_runtime,
        )

    async def start(self, role_name: str) -> tuple[str, str]:
        session_uid = uuid4().hex
        session = self.session_repo.create(session_uid=session_uid, role_name=role_name)
        message_fields = await self._generate_first_question_with_run(
            session=session,
            role_name=role_name,
        )
        self.message_repo.create(
            session_id=session.id,
            role_type="assistant",
            message_type="question",
            round_no=1,
            **message_fields,
        )
        self.db.commit()
        return session.session_uid, message_fields["content"]

    async def start_with_project(self, project_uid: str) -> tuple[str, str]:
        project = self.project_repo.get_by_uid(project_uid)
        if not project:
            raise HTTPException(status_code=404, detail="Preparation project not found")

        plan = self.plan_repo.get_latest_by_project_id(project.id)
        if not plan:
            raise HTTPException(status_code=400, detail="Interview plan is required before starting interview")

        role_name = self._role_name_from_plan(project.target_role, plan.content)
        session_uid = uuid4().hex
        session = self.session_repo.create(
            session_uid=session_uid,
            role_name=role_name,
            project_id=project.id,
            interview_plan_id=plan.id,
        )
        reply = self._first_question_from_plan(plan.content)
        raw_response = {"source": "interview_plan", "planId": plan.id}
        message_fields = {
            "content": reply,
            "raw_response": raw_response,
            "agent_run_id": None,
            "schema_version": None,
            "evidence_refs": [],
        }
        if not reply:
            message_fields = await self._generate_first_question_with_run(
                session=session,
                role_name=role_name,
                plan_context=self._plan_context(plan),
                plan=plan,
            )
        execution = self.execution_service.initialize(
            session_id=session.id,
            interview_plan_id=plan.id,
            plan_content=plan.content or {},
        )
        self.message_repo.create(
            session_id=session.id,
            role_type="assistant",
            message_type="question",
            round_no=1,
            **{
                **message_fields,
                "raw_response": {**(message_fields.get("raw_response") or {}), "executionId": execution.id},
            },
        )
        self.db.commit()
        return session.session_uid, message_fields["content"]

    async def chat(self, session_uid: str, message: str) -> tuple[str, int]:
        session = self._get_active_session(session_uid)
        try:
            result = await self.runtime_workflow.resume_with_user_input(session, message)
        except Exception:
            self.db.commit()
            raise
        self.db.commit()
        return result.reply, result.round_no

    async def end(self, session_uid: str) -> EvaluationResponse:
        session = self._get_session(session_uid)
        result = await self.assessment_workflow.run(session)
        saved = result.evaluation
        if saved is None:
            self.db.commit()
            return self._empty_evaluation_response()
        output_ids = await self._generate_project_outputs_if_needed(session, saved)
        self.assessment_workflow.record_project_outputs(
            result,
            project_candidate_profile_id=output_ids.get("project_candidate_profile_id"),
            resume_authenticity_report_id=output_ids.get("resume_authenticity_report_id"),
        )
        self.db.commit()
        return self._evaluation_to_response(saved)

    def history(self, session_uid: str) -> HistoryResponse:
        session = self._get_session(session_uid)
        messages = self.message_repo.list_by_session_id(session.id)
        evaluation = self.evaluation_repo.get_latest_by_session_id(session.id)
        return HistoryResponse(
            sessionId=session.session_uid,
            roleName=session.role_name,
            status=session.status,
            messages=[
                MessageResponse(
                    roleType=item.role_type,
                    messageType=item.message_type,
                    roundNo=item.round_no,
                    content=item.content,
                    createTime=item.create_time,
                )
                for item in messages
            ],
            evaluation=self._evaluation_to_response(evaluation) if evaluation else None,
        )
    
    def delete(self, session_uid: str) -> DeleteResponse:
        session = self._get_session(session_uid)
        existing_messages = self.message_repo.list_by_session_id(session.id)
        existing_evaluations = self.evaluation_repo.list_by_session_id(session.id)
        existing_summaries = self.summary_repo.list_by_session_id(session.id)
        execution = self.execution_repo.get_latest_by_session_id(session.id)

        if existing_messages:
            for message in existing_messages:
                self.message_repo.soft_delete(message)

        if existing_evaluations:
            for evaluation in existing_evaluations:
                self.evaluation_repo.soft_delete(evaluation)

        if existing_summaries:
            for summary in existing_summaries:
                self.summary_repo.soft_delete(summary)

        if execution:
            self.execution_repo.soft_delete(execution)

        self.session_repo.soft_delete(session)
        self.db.commit()
        return DeleteResponse(success=True)

    def execution(self, session_uid: str) -> dict:
        session = self._get_session(session_uid)
        execution = self.execution_service.get_latest(session.id)
        return self.execution_service.response(execution)

    async def _generate_first_question_with_run(
        self,
        session,
        role_name: str,
        plan_context: str | None = None,
        plan=None,
    ):
        run_result = await self.interview_executor_agent.run(
            FirstQuestionAgentInput(
                session=session,
                role_name=role_name,
                plan_context=plan_context,
                plan=plan,
            )
        )
        return run_result.message_fields()

    async def _generate_followup_with_run(
        self,
        session,
        answer_message,
        recent_history,
        candidate_profile: str | None = None,
        conversation_summary: str | None = None,
        plan_context: str | None = None,
        execution_context: str | None = None,
        candidate_profile_id: int | None = None,
        conversation_summary_id: int | None = None,
        execution=None,
    ):
        run_result = await self.interview_executor_agent.run(
            FollowupAgentInput(
                session=session,
                answer_message=answer_message,
                recent_history=recent_history,
                candidate_profile=candidate_profile,
                conversation_summary=conversation_summary,
                plan_context=plan_context,
                execution_context=execution_context,
                candidate_profile_id=candidate_profile_id,
                conversation_summary_id=conversation_summary_id,
                execution=execution,
            )
        )
        return run_result.message_fields()

    async def _generate_memory_with_run(
        self,
        prompt_id: str,
        session_id: int,
        previous_content: str | None,
        profile_messages: list,
        previous_summary_id: int | None = None,
    ):
        session = self._get_session_by_id(session_id)
        run_result = await self.session_memory_agent.run(
            SessionMemoryAgentInput(
                prompt_id=prompt_id,
                session=session,
                session_id=session_id,
                previous_content=previous_content,
                profile_messages=profile_messages,
                previous_summary_id=previous_summary_id,
            )
        )

        return run_result.message_fields()

    async def _refresh_memory_if_needed(self, session_id: int, latest_completed_round_no: int) -> None:
        if latest_completed_round_no < 10:
            return

        latest_conversation = self.summary_repo.get_latest_by_session_id(session_id, "conversation")
        latest_profile = self.summary_repo.get_latest_by_session_id(session_id, "candidate_profile")
        profile_round = latest_profile.to_round_no if latest_profile else 0
        if not latest_profile or latest_completed_round_no - profile_round >= 10:
            profile_from_round_no = 1 if not latest_profile else latest_profile.to_round_no + 1
            profile_messages = self.message_repo.list_between_rounds(
                session_id,
                profile_from_round_no,
                latest_completed_round_no,
            )
            if profile_messages:
                try:
                    summary_fields = await self._generate_memory_with_run(
                        prompt_id="candidate_profile",
                        session_id=session_id,
                        previous_content=latest_profile.content if latest_profile else None,
                        profile_messages=profile_messages,
                        previous_summary_id=latest_profile.id if latest_profile else None,
                    )
                except Exception:
                    logger.warning("Failed to refresh candidate profile summary", exc_info=True)
                else:
                    self.summary_repo.create(
                        session_id=session_id,
                        summary_type="candidate_profile",
                        from_round_no=1,
                        to_round_no=latest_completed_round_no,
                        **summary_fields,
                    )

        last_summary_round = latest_conversation.to_round_no if latest_conversation else 0
        if latest_conversation and latest_completed_round_no - last_summary_round < 5:
            return

        from_round_no = 1 if not latest_conversation else latest_conversation.to_round_no + 1
        new_messages = self.message_repo.list_between_rounds(
            session_id,
            from_round_no,
            latest_completed_round_no,
        )
        if not new_messages:
            return

        try:
            summary_fields = await self._generate_memory_with_run(
                prompt_id="conversation_summary",
                session_id=session_id,
                previous_content=latest_conversation.content if latest_conversation else None,
                profile_messages=new_messages,
                previous_summary_id=latest_conversation.id if latest_conversation else None,
            )
        except Exception:
            logger.warning("Failed to refresh conversation summary", exc_info=True)
        else:
            self.summary_repo.create(
                session_id=session_id,
                summary_type="conversation",
                from_round_no=1,
                to_round_no=latest_completed_round_no,
                **summary_fields,
            )

    def _evaluation_context(self, session_id: int):
        latest_completed_round_no = self.message_repo.latest_completed_round_no(session_id)
        if latest_completed_round_no <= 15:
            return self.message_repo.list_by_session_id(session_id)
        return self.message_repo.list_recent_rounds(session_id, rounds=8)

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
        return self.execution_service.context_for_followup(execution, plan.content if plan else None)

    async def _advance_execution_if_needed(self, session, answer_message, recent_history):
        if not session.interview_plan_id:
            return None
        execution = self.execution_repo.get_active_by_session_id(session.id)
        if not execution:
            return None
        current_section = self.execution_service.current_section(execution)
        judge_result = None
        answer = answer_message.content
        round_no = answer_message.round_no
        if current_section:
            try:
                run_result = await self.topic_judge_agent.run(
                    TopicJudgeAgentInput(
                        session=session,
                        execution=execution,
                        current_section=current_section,
                        answer_message=answer_message,
                        recent_history=recent_history,
                    )
                )
            except Exception:
                logger.warning("Failed to judge topic completion", exc_info=True)
            else:
                judge_result = {
                    **(run_result.output or {}),
                    "agent_run_id": run_result.agent_run.id,
                    "schema_version": run_result.output_schema,
                    "evidence_refs": run_result.evidence_refs,
                }
        return self.execution_service.advance_after_answer(execution, answer, round_no, judge_result)

    def _plan_context(self, plan) -> str:
        content = plan.content or {}
        return (
            f"InterviewPlan mode: {plan.plan_mode}\n"
            f"Role: {content.get('role_name') or content.get('roleName') or ''}\n"
            f"Sections: {content.get('sections', [])}\n"
            f"Evaluation rubric: {content.get('evaluation_rubric') or content.get('evaluationRubric') or []}"
        )

    def _first_question_from_plan(self, plan_content: dict) -> str | None:
        sections = plan_content.get("sections") or []
        if not sections:
            return None
        first_section = sections[0]
        questions = first_section.get("seed_questions") or first_section.get("seedQuestions") or []
        return questions[0] if questions else None

    def _role_name_from_plan(self, target_role: str | None, plan_content: dict) -> str:
        return (
            target_role
            or plan_content.get("role_name")
            or plan_content.get("roleName")
            or "目标岗位"
        )


    def _get_session(self, session_uid: str):
        session = self.session_repo.get_by_uid(session_uid)
        if not session:
            raise HTTPException(status_code=404, detail="Interview session not found")
        return session

    def _get_session_by_id(self, session_id: int):
        return self.session_repo.get_by_id(session_id)

    def _get_active_session(self, session_uid: str):
        session = self._get_session(session_uid)
        if session.status != "active":
            raise HTTPException(status_code=400, detail="Interview session is not active")
        return session

    def _evaluation_to_response(self, evaluation) -> EvaluationResponse:
        return EvaluationResponse(
            strengths=evaluation.strengths or "",
            weaknesses=evaluation.weaknesses or "",
            suggestions=evaluation.suggestions or "",
            technicalAbility=evaluation.technical_ability or "",
            projectExperience=evaluation.project_experience or "",
            communication=evaluation.communication or "",
            improvementSuggestions=evaluation.improvement_suggestions or "",
            summary=evaluation.summary,
        )

    def _empty_evaluation_response(self) -> EvaluationResponse:
        return EvaluationResponse(
            strengths="",
            weaknesses="",
            suggestions="",
            technicalAbility="",
            projectExperience="",
            communication="",
            improvementSuggestions="",
            summary=None,
        )

    async def _generate_project_outputs_if_needed(self, session, evaluation) -> dict[str, int]:
        output_ids: dict[str, int] = {}
        if not session.project_id:
            return output_ids

        execution = self.execution_repo.get_latest_by_session_id(session.id)
        messages = self.message_repo.list_by_session_id(session.id)
        evaluation_payload = {
            "strengths": evaluation.strengths,
            "weaknesses": evaluation.weaknesses,
            "suggestions": evaluation.suggestions,
            "technical_ability": evaluation.technical_ability,
            "project_experience": evaluation.project_experience,
            "communication": evaluation.communication,
            "improvement_suggestions": evaluation.improvement_suggestions,
            "summary": evaluation.summary,
        }
        service = PreparationService(self.db)
        try:
            candidate_profile = await service.generate_candidate_profile_for_project(
                project_id=session.project_id,
                target_role=session.role_name,
                source_session_id=session.id,
                execution_state=execution.state if execution else None,
                evaluation=evaluation_payload,
                transcript_messages=messages,
            )
            output_ids["project_candidate_profile_id"] = candidate_profile.id
            resume_authenticity = await service.generate_resume_authenticity_for_latest_resume(
                project_id=session.project_id,
                session_id=session.id,
                execution_state=execution.state if execution else None,
                evaluation=evaluation_payload,
                transcript_messages=messages,
            )
            if resume_authenticity:
                output_ids["resume_authenticity_report_id"] = resume_authenticity.id
        except Exception:
            logger.warning("Failed to generate project outputs", exc_info=True)
        return output_ids
