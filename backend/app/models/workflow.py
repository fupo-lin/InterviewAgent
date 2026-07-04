from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.config.database import Base


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workflow_run_id: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    workflow_id: Mapped[str] = mapped_column(String(80), nullable=False)
    thread_id: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    project_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("preparation_projects.id"),
        nullable=True,
    )
    session_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("interview_sessions.id"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(30), default="running", nullable=False)
    current_step: Mapped[str | None] = mapped_column(String(80), nullable=True)
    state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
