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
from app.repository.preparation_repository import InterviewPlanRepository, PreparationProjectRepository
from app.service.interview_execution_service import InterviewExecutionService
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
        self.execution_service = InterviewExecutionService(self.execution_repo)
        self.project_repo = PreparationProjectRepository(db)
        self.plan_repo = InterviewPlanRepository(db)
        self.llm = LLMService()

    async def start(self, role_name: str) -> tuple[str, str]:
        session_uid = uuid4().hex
        session = self.session_repo.create(session_uid=session_uid, role_name=role_name)
        reply, raw_response = await self.llm.generate_first_question(role_name)
        self.message_repo.create(
            session_id=session.id,
            role_type="assistant",
            message_type="question",
            round_no=1,
            content=reply,
            raw_response=raw_response,
        )
        self.db.commit()
        return session.session_uid, reply

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
        if not reply:
            reply, raw_response = await self.llm.generate_first_question(
                role_name,
                plan_context=self._plan_context(plan),
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
            content=reply,
            raw_response={**(raw_response or {}), "executionId": execution.id},
        )
        self.db.commit()
        return session.session_uid, reply

    async def chat(self, session_uid: str, message: str) -> tuple[str, int]:
        session = self._get_active_session(session_uid)
        round_no = self.message_repo.latest_assistant_question_round_no(session.id)
        self.message_repo.create(
            session_id=session.id,
            role_type="user",
            message_type="answer",
            round_no=round_no,
            content=message,
        )

        latest_completed_round_no = self.message_repo.latest_completed_round_no(session.id)
        recent_history = self.message_repo.list_recent_rounds(session.id, rounds=4)
        execution = await self._advance_execution_if_needed(session, message, round_no, recent_history)
        await self._refresh_memory_if_needed(session.id, latest_completed_round_no)
        candidate_profile = self.summary_repo.get_latest_by_session_id(session.id, "candidate_profile")
        conversation_summary = self.summary_repo.get_latest_by_session_id(session.id, "conversation")
        plan_context = self._session_plan_context(session)
        execution_context = self._session_execution_context(session, execution)
        reply, raw_response = await self.llm.generate_followup(
            session.role_name,
            message,
            recent_history,
            candidate_profile=candidate_profile.content if candidate_profile else None,
            conversation_summary=conversation_summary.content if conversation_summary else None,
            plan_context=plan_context,
            execution_context=execution_context,
        )
        self.message_repo.create(
            session_id=session.id,
            role_type="assistant",
            message_type="followup",
            round_no=round_no + 1,
            content=reply,
            raw_response={**(raw_response or {}), "execution": self.execution_service.response(execution) if execution else None},
        )
        self.db.commit()
        return reply, round_no + 1

    async def end(self, session_uid: str) -> EvaluationResponse:
        session = self._get_session(session_uid)
        existing = self.evaluation_repo.get_latest_by_session_id(session.id)
        if existing:
            self.session_repo.mark_finished(session)
            self.execution_service.mark_finished(session.id)
            self.db.commit()
            return self._evaluation_to_response(existing)

        history = self._evaluation_context(session.id)
        candidate_profile = self.summary_repo.get_latest_by_session_id(session.id, "candidate_profile")
        conversation_summary = self.summary_repo.get_latest_by_session_id(session.id, "conversation")
        evaluation, _raw_response = await self.llm.generate_evaluation(
            history,
            candidate_profile=candidate_profile.content if candidate_profile else None,
            conversation_summary=conversation_summary.content if conversation_summary else None,
            plan_context=self._session_plan_context(session),
        )
        saved = self.evaluation_repo.create(
            session_id=session.id,
            strengths=evaluation["strengths"],
            weaknesses=evaluation["weaknesses"],
            suggestions=evaluation["suggestions"],
            summary=evaluation.get("summary"),
            technical_ability=evaluation.get("technical_ability"),
            project_experience=evaluation.get("project_experience"),
            communication=evaluation.get("communication"),
            improvement_suggestions=evaluation.get("improvement_suggestions"),
        )
        self.session_repo.mark_finished(session)
        self.execution_service.mark_finished(session.id)
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
                    profile_content, profile_raw = await self.llm.generate_candidate_profile(
                        latest_profile.content if latest_profile else None,
                        profile_messages,
                    )
                except Exception:
                    logger.warning("Failed to refresh candidate profile summary", exc_info=True)
                else:
                    self.summary_repo.create(
                        session_id=session_id,
                        summary_type="candidate_profile",
                        from_round_no=1,
                        to_round_no=latest_completed_round_no,
                        content=profile_content,
                        raw_response=profile_raw,
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
            summary_content, summary_raw = await self.llm.generate_conversation_summary(
                latest_conversation.content if latest_conversation else None,
                new_messages,
            )
        except Exception:
            logger.warning("Failed to refresh conversation summary", exc_info=True)
        else:
            self.summary_repo.create(
                session_id=session_id,
                summary_type="conversation",
                from_round_no=1,
                to_round_no=latest_completed_round_no,
                content=summary_content,
                raw_response=summary_raw,
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

    async def _advance_execution_if_needed(self, session, answer: str, round_no: int, recent_history):
        if not session.interview_plan_id:
            return None
        execution = self.execution_repo.get_active_by_session_id(session.id)
        if not execution:
            return None
        current_section = self.execution_service.current_section(execution)
        judge_result = None
        if current_section:
            try:
                judge_result, _raw_response = await self.llm.judge_topic_completion(
                    current_section=current_section,
                    execution_state=execution.state or {},
                    user_answer=answer,
                    recent_history=recent_history,
                )
            except Exception:
                logger.warning("Failed to judge topic completion", exc_info=True)
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
