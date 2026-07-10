import unittest
from types import SimpleNamespace

from service.support import configure_backend_imports

configure_backend_imports()

from app.service.rag_pipeline import (
    HybridKnowledgeRetriever,
    KnowledgeDocumentInput,
    KnowledgeIndexer,
    SimpleTextChunker,
)
from app.service.retrieval_tools import LocalKnowledgeRetriever


class FakeDocumentRepo:
    def __init__(self):
        self.items = []

    def get_by_source(self, **kwargs):
        for item in reversed(self.items):
            if (
                item.source_type == kwargs["source_type"]
                and item.source_id == kwargs["source_id"]
                and item.project_id == kwargs.get("project_id")
                and item.session_id == kwargs.get("session_id")
                and item.status != "deleted"
            ):
                return item
        return None

    def create(self, **kwargs):
        item = SimpleNamespace(id=len(self.items) + 1, status="active", **kwargs)
        self.items.append(item)
        return item

    def save(self, item):
        return item


class FakeChunkRepo:
    def __init__(self):
        self.items = []

    def delete_by_document_id(self, document_id):
        for item in self.items:
            if item.document_id == document_id:
                item.status = "deleted"

    def list_by_document_id(self, document_id):
        return [
            item
            for item in self.items
            if item.document_id == document_id and item.status != "deleted"
        ]

    def create_many(self, chunks):
        created = []
        for chunk in chunks:
            item = SimpleNamespace(id=len(self.items) + 1, **chunk)
            self.items.append(item)
            created.append(item)
        return created

    def list(self, project_id=None, session_id=None, source_types=None, limit=500):
        items = [item for item in self.items if item.status != "deleted"]
        if project_id is not None:
            items = [item for item in items if item.project_id == project_id]
        if session_id is not None:
            items = [item for item in items if item.session_id == session_id]
        if source_types:
            items = [item for item in items if item.source_type in source_types]
        return list(reversed(items))[:limit]


class FakeArtifactRepo:
    def __init__(self, item=None):
        self.item = item

    def get_latest_by_project_id(self, project_id):
        return self.item


class FakeMessageRepo:
    def list_by_session_id(self, session_id):
        return []


class RagPipelineTest(unittest.TestCase):
    def test_indexer_chunks_and_reuses_same_document_hash(self):
        document_repo = FakeDocumentRepo()
        chunk_repo = FakeChunkRepo()
        indexer = KnowledgeIndexer(
            document_repo=document_repo,
            chunk_repo=chunk_repo,
            chunker=SimpleTextChunker(chunk_tokens=5, overlap_tokens=1),
        )
        document = KnowledgeDocumentInput(
            project_id=1,
            session_id=None,
            source_type="resume_profile",
            source_id=10,
            title="resume",
            content="Redis cache reduced latency MySQL schema optimized throughput",
        )

        first = indexer.index(document)
        second = indexer.index(document)

        self.assertGreater(len(first), 1)
        self.assertEqual([item.id for item in first], [item.id for item in second])
        self.assertEqual(len(document_repo.items), 1)

    def test_hybrid_retriever_finds_relevant_chunk(self):
        document_repo = FakeDocumentRepo()
        chunk_repo = FakeChunkRepo()
        indexer = KnowledgeIndexer(
            document_repo=document_repo,
            chunk_repo=chunk_repo,
            chunker=SimpleTextChunker(chunk_tokens=8, overlap_tokens=0),
        )
        indexer.index(
            KnowledgeDocumentInput(
                project_id=1,
                session_id=None,
                source_type="resume_profile",
                source_id=10,
                content=(
                    "Redis cache reduced latency for hot keys. "
                    "Message queue improved async processing."
                ),
            )
        )
        retriever = HybridKnowledgeRetriever(chunk_repo=chunk_repo)

        found = retriever.search(
            query="Redis latency",
            project_id=1,
            source_types=["resume_profile"],
            limit=1,
        )

        self.assertEqual(len(found), 1)
        self.assertIn("redis", found[0].content.lower())
        self.assertEqual(found[0].metadata["retrieval"], "hybrid")

    def test_local_retriever_refreshes_project_index_before_search(self):
        document_repo = FakeDocumentRepo()
        chunk_repo = FakeChunkRepo()
        indexer = KnowledgeIndexer(
            document_repo=document_repo,
            chunk_repo=chunk_repo,
            chunker=SimpleTextChunker(chunk_tokens=8, overlap_tokens=0),
        )
        hybrid = HybridKnowledgeRetriever(chunk_repo=chunk_repo)
        retriever = LocalKnowledgeRetriever(
            message_repo=FakeMessageRepo(),
            resume_profile_repo=FakeArtifactRepo(
                SimpleNamespace(
                    id=31,
                    resume_id=41,
                    content={"skills": ["Redis", "MySQL"], "summary": "Redis cache latency"},
                )
            ),
            jd_analysis_repo=FakeArtifactRepo(None),
            gap_analysis_repo=FakeArtifactRepo(None),
            project_candidate_profile_repo=FakeArtifactRepo(None),
            knowledge_indexer=indexer,
            hybrid_retriever=hybrid,
        )

        found = retriever.search_technology(project_id=1, query="Redis latency", limit=3)

        self.assertGreaterEqual(len(found), 1)
        self.assertEqual(found[0].metadata["retrieval"], "hybrid")
        self.assertGreaterEqual(len(chunk_repo.items), 1)


if __name__ == "__main__":
    unittest.main()
