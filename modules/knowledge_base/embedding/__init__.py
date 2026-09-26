from modules.knowledge_base.embedding.fake_provider import FakeEmbeddingProvider
from modules.knowledge_base.embedding.self_hosted import SelfHostedEmbeddingProvider
from modules.knowledge_base.embedding.api_provider import APIEmbeddingProvider
from modules.knowledge_base.embedding.adapter import EmbeddingAdapter
from modules.knowledge_base.embedding.record import EmbeddingRecord
from modules.knowledge_base.embedding.engine import (
    KnowledgeEmbeddingEngine,
    EmbeddingBatchResult,
)
from modules.knowledge_base.embedding.repository import (
    IEmbeddingRepository,
    CanonicalEmbeddingRepository,
)
from modules.knowledge_base.embedding.pipeline import (
    R4EmbeddingPipeline,
    R4PipelineSummary,
)

__all__ = [
    "FakeEmbeddingProvider",
    "SelfHostedEmbeddingProvider",
    "APIEmbeddingProvider",
    "EmbeddingAdapter",
    "EmbeddingRecord",
    "KnowledgeEmbeddingEngine",
    "EmbeddingBatchResult",
    "IEmbeddingRepository",
    "CanonicalEmbeddingRepository",
    "R4EmbeddingPipeline",
    "R4PipelineSummary",
]
