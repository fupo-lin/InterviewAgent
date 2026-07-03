from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent import AgentEvidenceItem, AgentRun


class AgentRunRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, agent_run_id: int) -> AgentRun | None:
        statement = select(AgentRun).where(AgentRun.id == agent_run_id)
        return self.db.scalars(statement).first()

    def list(
        self,
        project_id: int | None = None,
        session_id: int | None = None,
        status: str | None = None,
        agent_name: str | None = None,
        prompt_id: str | None = None,
        limit: int = 50,
    ) -> list[AgentRun]:
        statement = select(AgentRun)
        if project_id is not None:
            statement = statement.where(AgentRun.project_id == project_id)
        if session_id is not None:
            statement = statement.where(AgentRun.session_id == session_id)
        if status:
            statement = statement.where(AgentRun.status == status)
        if agent_name:
            statement = statement.where(AgentRun.agent_name == agent_name)
        if prompt_id:
            statement = statement.where(AgentRun.prompt_id == prompt_id)
        statement = statement.order_by(AgentRun.id.desc()).limit(limit)
        return list(self.db.scalars(statement).all())

    def list_failed(
        self,
        project_id: int | None = None,
        session_id: int | None = None,
        limit: int = 50,
    ) -> list[AgentRun]:
        return self.list(
            project_id=project_id,
            session_id=session_id,
            status="failed",
            limit=limit,
        )

    def get_latest_success_by_context(
        self,
        session_id: int,
        prompt_id: str,
        context_refs: dict,
        limit: int = 50,
    ) -> AgentRun | None:
        candidates = self.list(
            session_id=session_id,
            status="success",
            prompt_id=prompt_id,
            limit=limit,
        )
        for run in candidates:
            run_context_refs = run.context_refs or {}
            if all(run_context_refs.get(key) == value for key, value in context_refs.items()):
                return run
        return None


class AgentEvidenceItemRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_by_agent_run_id(self, agent_run_id: int) -> list[AgentEvidenceItem]:
        statement = (
            select(AgentEvidenceItem)
            .where(AgentEvidenceItem.agent_run_id == agent_run_id)
            .order_by(AgentEvidenceItem.id.asc())
        )
        return list(self.db.scalars(statement).all())

    def list(
        self,
        project_id: int | None = None,
        session_id: int | None = None,
        evidence_type: str | None = None,
        source_type: str | None = None,
        prompt_id: str | None = None,
        limit: int = 100,
    ) -> list[AgentEvidenceItem]:
        statement = select(AgentEvidenceItem)
        if project_id is not None:
            statement = statement.where(AgentEvidenceItem.project_id == project_id)
        if session_id is not None:
            statement = statement.where(AgentEvidenceItem.session_id == session_id)
        if evidence_type:
            statement = statement.where(AgentEvidenceItem.evidence_type == evidence_type)
        if source_type:
            statement = statement.where(AgentEvidenceItem.source_type == source_type)
        if prompt_id:
            statement = statement.where(AgentEvidenceItem.prompt_id == prompt_id)
        statement = statement.order_by(AgentEvidenceItem.id.desc()).limit(limit)
        return list(self.db.scalars(statement).all())
