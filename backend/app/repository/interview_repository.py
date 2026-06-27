from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.interview import InterviewEvaluation, InterviewMessage, InterviewSession


class InterviewSessionRepository:
    def __init__(self, db: Session):
        self.db = db

#
    def create(self, session_uid: str, role_name: str) -> InterviewSession:
        session = InterviewSession(session_uid=session_uid, role_name=role_name, status="active") # 在内存中创建一个Python对象
        self.db.add(session) # 加入Session的工作区，此时还没有进入数据库
        self.db.flush() # flush()会把内存中的对象同步到数据库中，但不会提交事务。此时session.id就有值了
        return session #返回带有 ID 的对象供后续使用

    def get_by_uid(self, session_uid: str) -> InterviewSession | None:
        statement = select(InterviewSession).where(
            InterviewSession.session_uid == session_uid,
            InterviewSession.status != "deleted",
        )
        return self.db.scalars(statement).first()

    def mark_finished(self, session: InterviewSession) -> InterviewSession:
        session.status = "finished"
        self.db.flush()
        return session
    
    def soft_delete(self, session: InterviewSession) -> InterviewSession:
        session.status = "deleted"
        self.db.flush()
        return session


class InterviewMessageRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        session_id: int,
        role_type: str,
        message_type: str,
        round_no: int,
        content: str,
        raw_response: dict | None = None,
    ) -> InterviewMessage:
        message = InterviewMessage(
            session_id=session_id,
            role_type=role_type,
            message_type=message_type,
            round_no=round_no,
            content=content,
            raw_response=raw_response,
        )
        self.db.add(message)
        self.db.flush()
        return message

    def list_by_session_id(self, session_id: int) -> list[InterviewMessage]:
        statement = (
            select(InterviewMessage)
            .where(InterviewMessage.session_id == session_id, InterviewMessage.status != "deleted")
            .order_by(InterviewMessage.round_no.asc(), InterviewMessage.id.asc())
        )
        return list(self.db.scalars(statement).all())

    def next_answer_round_no(self, session_id: int) -> int:
        messages = self.list_by_session_id(session_id)
        user_rounds = [message.round_no for message in messages if message.role_type == "user"]
        if not user_rounds:
            return 1
        return max(user_rounds) + 1
    
    def soft_delete(self, message: InterviewMessage) -> InterviewMessage:
        message.status = "deleted"
        self.db.flush()
        return message


class InterviewEvaluationRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        session_id: int,
        strengths: str,
        weaknesses: str,
        suggestions: str,
        summary: str | None = None,
        technical_ability: str | None = None,
        project_experience: str | None = None,
        communication: str | None = None,
        improvement_suggestions: str | None = None,
    ) -> InterviewEvaluation:
        evaluation = InterviewEvaluation(
            session_id=session_id,
            strengths=strengths,
            weaknesses=weaknesses,
            suggestions=suggestions,
            summary=summary,
            technical_ability=technical_ability,
            project_experience=project_experience,
            communication=communication,
            improvement_suggestions=improvement_suggestions,
        )
        self.db.add(evaluation)
        self.db.flush()
        return evaluation

    def get_latest_by_session_id(self, session_id: int) -> InterviewEvaluation | None:
        statement = (
            select(InterviewEvaluation)
            .where(InterviewEvaluation.session_id == session_id, InterviewEvaluation.status != "deleted")
            .order_by(InterviewEvaluation.id.desc())
        )
        return self.db.scalars(statement).first()

    def list_by_session_id(self, session_id: int) -> list[InterviewEvaluation]:
        statement = select(InterviewEvaluation).where(
            InterviewEvaluation.session_id == session_id,
            InterviewEvaluation.status != "deleted",
        )
        return list(self.db.scalars(statement).all())
    
    def soft_delete(self, evaluation: InterviewEvaluation) -> InterviewEvaluation:
        evaluation.status = "deleted"
        self.db.flush()
        return evaluation   
