from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.repository.interview_repository import (
    InterviewEvaluationRepository,
    InterviewMessageRepository,
    InterviewSessionRepository,
)
from app.schemas.interview import DeleteResponse, EvaluationResponse, HistoryResponse, MessageResponse
from app.service.llm_service import LLMService


class InterviewService:
    def __init__(self, db: Session):
        self.db = db
        self.session_repo = InterviewSessionRepository(db)
        self.message_repo = InterviewMessageRepository(db)
        self.evaluation_repo = InterviewEvaluationRepository(db)
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
        round_no = self.message_repo.next_answer_round_no(session.id)
        self.message_repo.create(
            session_id=session.id,
            role_type="user",
            message_type="answer",
            round_no=round_no,
            content=message,
        )

        history = self.message_repo.list_by_session_id(session.id)
        reply, raw_response = await self.llm.generate_followup(session.role_name, message, history)
        self.message_repo.create(
            session_id=session.id,
            role_type="assistant",
            message_type="followup",
            round_no=round_no,
            content=reply,
            raw_response=raw_response,
        )
        self.db.commit()
        return reply, round_no

    async def end(self, session_uid: str) -> EvaluationResponse:
        session = self._get_session(session_uid)
        existing = self.evaluation_repo.get_latest_by_session_id(session.id)
        if existing:
            self.session_repo.mark_finished(session)
            self.db.commit()
            return self._evaluation_to_response(existing)

        history = self.message_repo.list_by_session_id(session.id)
        evaluation, _raw_response = await self.llm.generate_evaluation(history)
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

        if existing_messages:
            for message in existing_messages:
                self.message_repo.soft_delete(message)

        if existing_evaluations:
            for evaluation in existing_evaluations:
                self.evaluation_repo.soft_delete(evaluation)

        self.session_repo.soft_delete(session)
        self.db.commit()
        return DeleteResponse(success=True)


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
