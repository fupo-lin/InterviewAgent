from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.knowledge import KnowledgeChunk, KnowledgeDocument


class KnowledgeDocumentRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_source(
        self,
        *,
        source_type: str,
        source_id: int | None,
        project_id: int | None = None,
        session_id: int | None = None,
    ) -> KnowledgeDocument | None:
        statement = select(KnowledgeDocument).where(
            KnowledgeDocument.source_type == source_type,
            KnowledgeDocument.source_id == source_id,
            KnowledgeDocument.status != "deleted",
        )
        if project_id is not None:
            statement = statement.where(KnowledgeDocument.project_id == project_id)
        if session_id is not None:
            statement = statement.where(KnowledgeDocument.session_id == session_id)
        return self.db.scalars(statement.order_by(KnowledgeDocument.id.desc())).first()

    def create(
        self,
        *,
        project_id: int | None,
        session_id: int | None,
        source_type: str,
        source_id: int | None,
        title: str | None,
        content_hash: str,
        metadata: dict | None = None,
    ) -> KnowledgeDocument:
        item = KnowledgeDocument(
            project_id=project_id,
            session_id=session_id,
            source_type=source_type,
            source_id=source_id,
            title=title,
            content_hash=content_hash,
            item_metadata=metadata or {},
            status="active",
        )
        self.db.add(item)
        self.db.flush()
        return item

    def save(self, item: KnowledgeDocument) -> KnowledgeDocument:
        self.db.flush()
        return item


class KnowledgeChunkRepository:
    def __init__(self, db: Session):
        self.db = db

    def delete_by_document_id(self, document_id: int) -> None:
        chunks = self.list_by_document_id(document_id)
        for item in chunks:
            item.status = "deleted"
        self.db.flush()

    def list_by_document_id(self, document_id: int) -> list[KnowledgeChunk]:
        statement = (
            select(KnowledgeChunk)
            .where(
                KnowledgeChunk.document_id == document_id,
                KnowledgeChunk.status != "deleted",
            )
            .order_by(KnowledgeChunk.chunk_index.asc())
        )
        return list(self.db.scalars(statement).all())

    def list(
        self,
        *,
        project_id: int | None = None,
        session_id: int | None = None,
        source_types: list[str] | None = None,
        limit: int = 500,
    ) -> list[KnowledgeChunk]:
        statement = select(KnowledgeChunk).where(KnowledgeChunk.status != "deleted")
        if project_id is not None:
            statement = statement.where(KnowledgeChunk.project_id == project_id)
        if session_id is not None:
            statement = statement.where(KnowledgeChunk.session_id == session_id)
        if source_types:
            statement = statement.where(KnowledgeChunk.source_type.in_(source_types))
        statement = statement.order_by(KnowledgeChunk.id.desc()).limit(limit)
        return list(self.db.scalars(statement).all())

    def create_many(
        self,
        chunks: list[dict],
    ) -> list[KnowledgeChunk]:
        items = [KnowledgeChunk(**chunk) for chunk in chunks]
        for item in items:
            self.db.add(item)
        self.db.flush()
        return items
