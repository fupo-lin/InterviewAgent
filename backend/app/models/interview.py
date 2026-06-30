from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config.database import Base

##数据库表的映射 --  对应到了数据库表的结构，对于表中的字段进行约束和设置默认值

class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("preparation_projects.id"), nullable=True)
    interview_plan_id: Mapped[int | None] = mapped_column(ForeignKey("interview_plans.id"), nullable=True)
    session_uid: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    role_name: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
# relationship() -- back_populates：建立双向绑定
# cascade="all, delete-orphan"：级联删除。当你删除一场Session时，
# 数据库会自动把这场面试下的所有消息（Messages）和评价（Evaluations）一并删除，防止产生垃圾数据。
    messages: Mapped[list["InterviewMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )
    evaluations: Mapped[list["InterviewEvaluation"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )
    summaries: Mapped[list["InterviewSummary"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )
    plan_executions: Mapped[list["InterviewPlanExecution"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )


class InterviewMessage(Base):

    __tablename__ = "interview_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("interview_sessions.id"), nullable=False)
    role_type: Mapped[str] = mapped_column(String(20), nullable=False)
    message_type: Mapped[str] = mapped_column(String(20), nullable=False)
    round_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    raw_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    session: Mapped[InterviewSession] = relationship(back_populates="messages")


class InterviewEvaluation(Base):
    __tablename__ = "interview_evaluations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("interview_sessions.id"), nullable=False)
    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    schema_version: Mapped[str] = mapped_column(String(80), default="InterviewEvaluation.v1", nullable=False)
    evidence_refs: Mapped[list | None] = mapped_column(JSON, nullable=True)
    strengths: Mapped[str | None] = mapped_column(Text, nullable=True)
    weaknesses: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggestions: Mapped[str | None] = mapped_column(Text, nullable=True)
    technical_ability: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_experience: Mapped[str | None] = mapped_column(Text, nullable=True)
    communication: Mapped[str | None] = mapped_column(Text, nullable=True)
    improvement_suggestions: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    session: Mapped[InterviewSession] = relationship(back_populates="evaluations")


class InterviewSummary(Base):
    __tablename__ = "interview_summaries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("interview_sessions.id"), nullable=False)
    summary_type: Mapped[str] = mapped_column(String(30), default="conversation", nullable=False)
    from_round_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    to_round_no: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    raw_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    session: Mapped[InterviewSession] = relationship(back_populates="summaries")


class InterviewPlanExecution(Base):
    __tablename__ = "interview_plan_executions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("interview_sessions.id"), nullable=False)
    interview_plan_id: Mapped[int] = mapped_column(ForeignKey("interview_plans.id"), nullable=False)
    current_section_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    current_section_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_section_round_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_completed_round_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    state: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    session: Mapped[InterviewSession] = relationship(back_populates="plan_executions")
