from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.config.database import Base


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    agent_name: Mapped[str] = mapped_column(String(80), nullable=False)
    agent_version: Mapped[str | None] = mapped_column(String(30), nullable=True)
    task_name: Mapped[str] = mapped_column(String(80), nullable=False)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("preparation_projects.id"), nullable=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("interview_sessions.id"), nullable=True)
    input_schema_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    output_schema_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    prompt_id: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(30), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    input_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    context_refs: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evidence_refs: Mapped[list | None] = mapped_column(JSON, nullable=True)
    output_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    raw_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="success", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
