"""Sparse Representation Module for EarthMind C.2 Knowledge Base."""

from modules.knowledge_base.sparse.record import SparseRepresentationRecord
from modules.knowledge_base.sparse.fake_provider import FakeSparseProvider
from modules.knowledge_base.sparse.adapter import SparseRepresentationAdapter
from modules.knowledge_base.sparse.engine import KnowledgeSparseEngine, SparseBatchResult

__all__ = [
    "SparseRepresentationRecord",
    "FakeSparseProvider",
    "SparseRepresentationAdapter",
    "KnowledgeSparseEngine",
    "SparseBatchResult",
]
