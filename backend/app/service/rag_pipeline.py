from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.service.retrieval_contract import RetrievedKnowledge

if TYPE_CHECKING:
    from app.repository.knowledge_repository import (
        KnowledgeChunkRepository,
        KnowledgeDocumentRepository,
    )


TOKEN_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


@dataclass(frozen=True)
class KnowledgeDocumentInput:
    source_type: str
    source_id: int | None
    content: str
    project_id: int | None = None
    session_id: int | None = None
    title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChunkedText:
    chunk_index: int
    content: str
    keywords: tuple[str, ...]
    token_count: int
    content_hash: str


class SimpleTextChunker:
    def __init__(self, chunk_tokens: int = 120, overlap_tokens: int = 24) -> None:
        self.chunk_tokens = chunk_tokens
        self.overlap_tokens = overlap_tokens

    def chunk(self, content: str) -> list[ChunkedText]:
        tokens = self._tokens(content)
        if not tokens:
            return []
        chunks = []
        start = 0
        index = 0
        while start < len(tokens):
            end = min(len(tokens), start + self.chunk_tokens)
            chunk_tokens = tokens[start:end]
            text = " ".join(chunk_tokens)
            chunks.append(
                ChunkedText(
                    chunk_index=index,
                    content=text,
                    keywords=tuple(self._keywords(chunk_tokens)),
                    token_count=len(chunk_tokens),
                    content_hash=stable_hash(text),
                )
            )
            index += 1
            if end == len(tokens):
                break
            start = max(end - self.overlap_tokens, start + 1)
        return chunks

    def _tokens(self, content: str) -> list[str]:
        return [match.group(0).lower() for match in TOKEN_PATTERN.finditer(content or "")]

    def _keywords(self, tokens: list[str]) -> list[str]:
        seen = []
        for token in tokens:
            if len(token) <= 1:
                continue
            if token in seen:
                continue
            seen.append(token)
            if len(seen) >= 20:
                break
        return seen


class HashingTextEmbedder:
    model_name = "local_hashing_v1"

    def __init__(self, dimensions: int = 32) -> None:
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in self._tokens(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm <= 0:
            return vector
        return [value / norm for value in vector]

    def similarity(self, left: list[float] | None, right: list[float] | None) -> float:
        if not left or not right:
            return 0.0
        size = min(len(left), len(right))
        return sum(float(left[index]) * float(right[index]) for index in range(size))

    def _tokens(self, text: str) -> list[str]:
        return [match.group(0).lower() for match in TOKEN_PATTERN.finditer(text or "")]


class KnowledgeIndexer:
    def __init__(
        self,
        *,
        document_repo: "KnowledgeDocumentRepository",
        chunk_repo: "KnowledgeChunkRepository",
        chunker: SimpleTextChunker | None = None,
        embedder: HashingTextEmbedder | None = None,
    ) -> None:
        self.document_repo = document_repo
        self.chunk_repo = chunk_repo
        self.chunker = chunker or SimpleTextChunker()
        self.embedder = embedder or HashingTextEmbedder()

    def index(self, document_input: KnowledgeDocumentInput) -> list:
        content_hash = stable_hash(document_input.content)
        document = self.document_repo.get_by_source(
            source_type=document_input.source_type,
            source_id=document_input.source_id,
            project_id=document_input.project_id,
            session_id=document_input.session_id,
        )
        if document and document.content_hash == content_hash:
            existing = self.chunk_repo.list_by_document_id(document.id)
            if existing:
                return existing
        if not document:
            document = self.document_repo.create(
                project_id=document_input.project_id,
                session_id=document_input.session_id,
                source_type=document_input.source_type,
                source_id=document_input.source_id,
                title=document_input.title,
                content_hash=content_hash,
                metadata=document_input.metadata,
            )
        else:
            document.content_hash = content_hash
            document.title = document_input.title
            document.item_metadata = document_input.metadata or {}
            self.document_repo.save(document)
            self.chunk_repo.delete_by_document_id(document.id)

        chunks = self.chunker.chunk(document_input.content)
        return self.chunk_repo.create_many(
            [
                {
                    "document_id": document.id,
                    "project_id": document_input.project_id,
                    "session_id": document_input.session_id,
                    "source_type": document_input.source_type,
                    "source_id": document_input.source_id,
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content,
                    "content_hash": chunk.content_hash,
                    "token_count": chunk.token_count,
                    "embedding_model": self.embedder.model_name,
                    "embedding": self.embedder.embed(chunk.content),
                    "keywords": list(chunk.keywords),
                    "item_metadata": document_input.metadata or {},
                    "status": "active",
                }
                for chunk in chunks
            ]
        )


class HybridKnowledgeRetriever:
    def __init__(
        self,
        *,
        chunk_repo: "KnowledgeChunkRepository",
        embedder: HashingTextEmbedder | None = None,
    ) -> None:
        self.chunk_repo = chunk_repo
        self.embedder = embedder or HashingTextEmbedder()

    def search(
        self,
        *,
        query: str | None,
        project_id: int | None = None,
        session_id: int | None = None,
        source_types: list[str] | None = None,
        limit: int = 5,
    ) -> list[RetrievedKnowledge]:
        chunks = self.chunk_repo.list(
            project_id=project_id,
            session_id=session_id,
            source_types=source_types,
            limit=500,
        )
        query_text = query or ""
        query_embedding = self.embedder.embed(query_text)
        query_tokens = set(self._tokens(query_text))
        scored = []
        for chunk in chunks:
            vector_score = self.embedder.similarity(query_embedding, chunk.embedding or [])
            keyword_score = self._keyword_score(query_tokens, chunk.keywords or [], chunk.content)
            score = (0.65 * vector_score) + (0.35 * keyword_score)
            scored.append((score, vector_score, keyword_score, chunk))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            RetrievedKnowledge(
                source_name=f"{chunk.source_type}_chunk",
                source_type=chunk.source_type,
                source_id=chunk.source_id,
                content=chunk.content,
                score=max(0.0, score),
                metadata={
                    "chunk_id": chunk.id,
                    "document_id": chunk.document_id,
                    "chunk_index": chunk.chunk_index,
                    "retrieval": "hybrid",
                    "vector_score": vector_score,
                    "keyword_score": keyword_score,
                    "embedding_model": chunk.embedding_model,
                },
            )
            for score, vector_score, keyword_score, chunk in scored[:limit]
            if chunk.content
        ]

    def _keyword_score(self, query_tokens: set[str], keywords: list[str], content: str) -> float:
        if not query_tokens:
            return 0.0
        keyword_tokens = {str(item).lower() for item in keywords or []}
        content_tokens = set(self._tokens(content))
        hits = len(query_tokens & (keyword_tokens | content_tokens))
        return hits / max(len(query_tokens), 1)

    def _tokens(self, text: str) -> list[str]:
        return [match.group(0).lower() for match in TOKEN_PATTERN.finditer(text or "")]


def stable_hash(content: str) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()
