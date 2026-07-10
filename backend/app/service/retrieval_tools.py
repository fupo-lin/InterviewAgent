from __future__ import annotations

from typing import Any

from app.service.rag_pipeline import KnowledgeDocumentInput
from app.service.retrieval_contract import RetrievedKnowledge


class LocalKnowledgeRetriever:
    def __init__(
        self,
        *,
        message_repo,
        resume_profile_repo,
        jd_analysis_repo,
        gap_analysis_repo,
        project_candidate_profile_repo,
        job_description_repo=None,
        resume_document_repo=None,
        knowledge_indexer=None,
        hybrid_retriever=None,
    ) -> None:
        self.message_repo = message_repo
        self.resume_profile_repo = resume_profile_repo
        self.jd_analysis_repo = jd_analysis_repo
        self.gap_analysis_repo = gap_analysis_repo
        self.project_candidate_profile_repo = project_candidate_profile_repo
        self.job_description_repo = job_description_repo
        self.resume_document_repo = resume_document_repo
        self.knowledge_indexer = knowledge_indexer
        self.hybrid_retriever = hybrid_retriever

    def get_resume_profile(self, project_id: int | None) -> list[RetrievedKnowledge]:
        if not project_id:
            return []
        profile = self.resume_profile_repo.get_latest_by_project_id(project_id)
        if not profile:
            return []
        return [
            RetrievedKnowledge(
                source_name="resume_profile",
                source_type="resume_profile",
                source_id=profile.id,
                content=self._stringify(profile.content),
                score=1.0,
                metadata={"project_id": project_id, "resume_id": profile.resume_id},
            )
        ]

    def get_previous_answer(
        self,
        session_id: int,
        query: str | None = None,
        limit: int = 4,
    ) -> list[RetrievedKnowledge]:
        messages = self.message_repo.list_by_session_id(session_id)
        answers = [message for message in messages if message.role_type == "user"]
        scored = [
            (
                self._score(message.content, query),
                message,
            )
            for message in answers
        ]
        scored.sort(key=lambda item: (item[0], item[1].round_no), reverse=True)
        return [
            RetrievedKnowledge(
                source_name="previous_answer",
                source_type="interview_message",
                source_id=message.id,
                content=message.content,
                score=score,
                metadata={"session_id": session_id, "round_no": message.round_no},
            )
            for score, message in scored[:limit]
            if message.content
        ]

    def search_company_info(
        self,
        project_id: int | None,
        query: str | None = None,
        limit: int = 5,
    ) -> list[RetrievedKnowledge]:
        if not project_id:
            return []
        indexed = self._search_index(
            query=query,
            project_id=project_id,
            source_types=["job_description", "jd_analysis"],
            limit=limit,
        )
        if indexed:
            return indexed

        candidates: list[RetrievedKnowledge] = []
        jd = self._latest(self.job_description_repo, project_id)
        if jd:
            candidates.append(
                RetrievedKnowledge(
                    source_name="job_description",
                    source_type="job_description",
                    source_id=jd.id,
                    content=self._join(
                        [
                            getattr(jd, "company_name", None),
                            getattr(jd, "title", None),
                            getattr(jd, "raw_content", None),
                        ]
                    ),
                    metadata={
                        "project_id": project_id,
                        "company_name": getattr(jd, "company_name", None),
                        "source_url": getattr(jd, "source_url", None),
                    },
                )
            )
        jd_analysis = self.jd_analysis_repo.get_latest_by_project_id(project_id)
        if jd_analysis:
            candidates.append(
                RetrievedKnowledge(
                    source_name="jd_analysis",
                    source_type="jd_analysis",
                    source_id=jd_analysis.id,
                    content=self._stringify(jd_analysis.content),
                    metadata={"project_id": project_id},
                )
            )
        return self._rank(candidates, query, limit)

    def search_technology(
        self,
        project_id: int | None,
        query: str | None = None,
        limit: int = 5,
    ) -> list[RetrievedKnowledge]:
        if not project_id:
            return []
        indexed = self._search_index(
            query=query,
            project_id=project_id,
            source_types=[
                "resume_profile",
                "jd_analysis",
                "gap_analysis",
                "project_candidate_profile",
            ],
            limit=limit,
        )
        if indexed:
            return indexed

        candidates: list[RetrievedKnowledge] = []
        for source_name, repo in (
            ("resume_profile", self.resume_profile_repo),
            ("jd_analysis", self.jd_analysis_repo),
            ("gap_analysis", self.gap_analysis_repo),
            ("project_candidate_profile", self.project_candidate_profile_repo),
        ):
            item = repo.get_latest_by_project_id(project_id)
            if not item:
                continue
            candidates.append(
                RetrievedKnowledge(
                    source_name=source_name,
                    source_type=source_name,
                    source_id=item.id,
                    content=self._stringify(item.content),
                    metadata={"project_id": project_id},
                )
            )
        return self._rank(candidates, query, limit)

    def refresh_project_index(self, project_id: int | None) -> int:
        if not project_id or not self.knowledge_indexer:
            return 0
        indexed = 0
        for item in self._project_documents(project_id):
            chunks = self.knowledge_indexer.index(item)
            indexed += len(chunks)
        return indexed

    def _search_index(
        self,
        *,
        query: str | None,
        project_id: int,
        source_types: list[str],
        limit: int,
    ) -> list[RetrievedKnowledge]:
        if not self.hybrid_retriever:
            return []
        found = self.hybrid_retriever.search(
            query=query,
            project_id=project_id,
            source_types=source_types,
            limit=limit,
        )
        if found:
            return found
        self.refresh_project_index(project_id)
        return self.hybrid_retriever.search(
            query=query,
            project_id=project_id,
            source_types=source_types,
            limit=limit,
        )

    def _project_documents(self, project_id: int) -> list[KnowledgeDocumentInput]:
        documents = []
        jd = self._latest(self.job_description_repo, project_id)
        if jd:
            documents.append(
                KnowledgeDocumentInput(
                    project_id=project_id,
                    session_id=None,
                    source_type="job_description",
                    source_id=jd.id,
                    title=getattr(jd, "title", None),
                    content=self._join(
                        [
                            getattr(jd, "company_name", None),
                            getattr(jd, "title", None),
                            getattr(jd, "raw_content", None),
                        ]
                    ),
                    metadata={
                        "company_name": getattr(jd, "company_name", None),
                        "source_url": getattr(jd, "source_url", None),
                    },
                )
            )
        for source_type, repo in (
            ("resume_profile", self.resume_profile_repo),
            ("jd_analysis", self.jd_analysis_repo),
            ("gap_analysis", self.gap_analysis_repo),
            ("project_candidate_profile", self.project_candidate_profile_repo),
        ):
            item = repo.get_latest_by_project_id(project_id)
            if not item:
                continue
            documents.append(
                KnowledgeDocumentInput(
                    project_id=project_id,
                    session_id=None,
                    source_type=source_type,
                    source_id=item.id,
                    title=source_type,
                    content=self._stringify(item.content),
                    metadata={"project_id": project_id},
                )
            )
        return documents

    def _rank(
        self,
        candidates: list[RetrievedKnowledge],
        query: str | None,
        limit: int,
    ) -> list[RetrievedKnowledge]:
        ranked = [
            RetrievedKnowledge(
                source_name=item.source_name,
                source_type=item.source_type,
                source_id=item.source_id,
                content=item.content,
                score=self._score(item.content, query),
                metadata=item.metadata,
            )
            for item in candidates
            if item.content
        ]
        ranked.sort(key=lambda item: item.score, reverse=True)
        return ranked[:limit]

    def _latest(self, repo, project_id: int):
        if not repo:
            return None
        getter = getattr(repo, "get_latest_by_project_id", None)
        if not callable(getter):
            return None
        return getter(project_id)

    def _score(self, content: str, query: str | None) -> float:
        if not query:
            return 0.5 if content else 0.0
        terms = [term.lower() for term in query.split() if term.strip()]
        if not terms:
            return 0.5 if content else 0.0
        lowered = (content or "").lower()
        hits = sum(1 for term in terms if term in lowered)
        return hits / len(terms)

    def _join(self, values: list[Any]) -> str:
        return "\n".join(str(value) for value in values if value)

    def _stringify(self, value: Any) -> str:
        if isinstance(value, dict):
            parts = []
            for key, item in value.items():
                parts.append(f"{key}: {self._stringify(item)}")
            return "\n".join(parts)
        if isinstance(value, list):
            return "\n".join(self._stringify(item) for item in value)
        return "" if value is None else str(value)
