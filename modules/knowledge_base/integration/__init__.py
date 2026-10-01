"""Stage R13 RAG → B2 Integration module.

Provides RAGContextProvider integrating completed R1-R12 RAG retrieval pipeline
with B2 Context Manager via IRAGContextProvider protocol and RAGContextContract interface.
"""

from modules.knowledge_base.integration.provider import RAGContextProvider

__all__ = ["RAGContextProvider"]
