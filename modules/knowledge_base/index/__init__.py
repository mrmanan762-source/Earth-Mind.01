"""C.2 Knowledge Base Index Layer."""

from modules.knowledge_base.index.collection_strategy import KnowledgeCollectionMapper
from modules.knowledge_base.index.engine import KnowledgeIndexEngine
from modules.knowledge_base.index.fake_adapter import FakeIndexAdapter
from modules.knowledge_base.index.qdrant_adapter import QdrantIndexAdapter
from modules.knowledge_base.index.record import IndexBatchResult, IndexRecord

__all__ = [
    "IndexRecord",
    "IndexBatchResult",
    "KnowledgeCollectionMapper",
    "KnowledgeIndexEngine",
    "FakeIndexAdapter",
    "QdrantIndexAdapter",
]
