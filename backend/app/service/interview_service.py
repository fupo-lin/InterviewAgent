import logging
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.repository.interview_repository import (
    InterviewEvaluationRepository,
    InterviewMessageRepository,
    InterviewSessionRepository,
    InterviewSummaryRepository,
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
        await self._refresh_memory_if_needed(session.id, latest_completed_round_no)
        candidate_profile = self.summary_repo.get_latest_by_session_id(session.id, "candidate_profile")
        conversation_summary = self.summary_repo.get_latest_by_session_id(session.id, "conversation")
        recent_history = self.message_repo.list_recent_rounds(session.id, rounds=4)
        reply, raw_response = await self.llm.generate_followup(
            session.role_name,
            message,
            recent_history,
            candidate_profile=candidate_profile.content if candidate_profile else None,
            conversation_summary=conversation_summary.content if conversation_summary else None,
        )
        self.message_repo.create(
            session_id=session.id,
            role_type="assistant",
            message_type="followup",
            round_no=round_no + 1,
            content=reply,
            raw_response=raw_response,
        )
        self.db.commit()
        return reply, round_no + 1

    async def end(self, session_uid: str) -> EvaluationResponse:
        session = self._get_session(session_uid)
        existing = self.evaluation_repo.get_latest_by_session_id(session.id)
        if existing:
            self.session_repo.mark_finished(session)
            self.db.commit()
            return self._evaluation_to_response(existing)

        history = self._evaluation_context(session.id)
        candidate_profile = self.summary_repo.get_latest_by_session_id(session.id, "candidate_profile")
        conversation_summary = self.summary_repo.get_latest_by_session_id(session.id, "conversation")
        evaluation, _raw_response = await self.llm.generate_evaluation(
            history,
            candidate_profile=candidate_profile.content if candidate_profile else None,
            conversation_summary=conversation_summary.content if conversation_summary else None,
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

        if existing_messages:
            for message in existing_messages:
                self.message_repo.soft_delete(message)

        if existing_evaluations:
            for evaluation in existing_evaluations:
                self.evaluation_repo.soft_delete(evaluation)

        if existing_summaries:
            for summary in existing_summaries:
                self.summary_repo.soft_delete(summary)

        self.session_repo.soft_delete(session)
        self.db.commit()
        return DeleteResponse(success=True)

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
