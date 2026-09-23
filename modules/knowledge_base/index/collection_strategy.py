"""Collection Mapping Strategy for C.2 Knowledge Base Index Layer.

Abstracts the mapping from logical Knowledge Collections (domain concept)
to physical index collections (e.g., physical vector store collection name).
"""

from typing import Dict, Optional


class KnowledgeCollectionMapper:
    """Strategy for mapping logical Knowledge Collections to physical index collection names.

    Supports default global collection physical mapping while allowing collection-specific
    or prefixed/suffixed overrides without breaking RAG or storage independence.
    """

    def __init__(self, default_physical_collection: str = "earthmind_knowledge", collection_prefix: Optional[str] = None):
        self.default_physical_collection = default_physical_collection
        self.collection_prefix = collection_prefix or ""
        self._explicit_mappings: Dict[str, str] = {}

    def register_mapping(self, logical_collection: str, physical_collection: str) -> None:
        """Register an explicit mapping from a logical collection to a physical collection."""
        if not logical_collection or not logical_collection.strip():
            raise ValueError("Logical collection name cannot be empty.")
        if not physical_collection or not physical_collection.strip():
            raise ValueError("Physical collection name cannot be empty.")
        self._explicit_mappings[logical_collection.strip()] = physical_collection.strip()

    def get_physical_collection_name(self, logical_collection: Optional[str] = None) -> str:
        """Get physical index collection name for a given logical Knowledge Collection."""
        if not logical_collection or not logical_collection.strip():
            return self.default_physical_collection

        clean_logical = logical_collection.strip()
        if clean_logical in self._explicit_mappings:
            return self._explicit_mappings[clean_logical]

        if self.collection_prefix:
            return f"{self.collection_prefix}{clean_logical.lower()}"

        return self.default_physical_collection
