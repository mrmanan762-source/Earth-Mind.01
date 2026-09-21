from typing import Dict, Any, List
from core.config.settings import settings
from core.interfaces.storage import IKnowledgeIndex

class KnowledgeIndexPlaceholder(IKnowledgeIndex):
    """Placeholder interface boundary for derived retrieval index.

    Rule: Retrieval indices are derived and rebuildable from canonical records.
    The index is never the authoritative source of truth.
    Physical vector engines (e.g. Qdrant) are deferred to future adapters.
    """

    def __init__(self, backend_name: str = settings.kb_storage.kb_index_backend):
        self.backend_name = backend_name
        self._registered_records: List[Dict[str, Any]] = []

    def index_status(self) -> Dict[str, Any]:
        """Get derived index status and health metadata."""
        return {
            "status": "PLACEHOLDER_READY",
            "backend": self.backend_name,
            "derived_from_canonical": True,
            "authoritative": False,
            "record_count": len(self._registered_records),
            "physical_vector_db": None,
        }

    def register_index_record(self, record: Dict[str, Any]) -> str:
        """Register a logical index record in the derived index placeholder."""
        rec_id = record.get("index_id") or record.get("chunk_id") or f"idx_{len(self._registered_records) + 1}"
        entry = {
            "index_id": rec_id,
            "derived_record": record,
            "status": "REGISTERED_DERIVED"
        }
        self._registered_records.append(entry)
        return rec_id

    def search_placeholder(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Placeholder query method indicating physical retrieval search is deferred."""
        return [
            {
                "query": query,
                "status": "SEARCH_DEFERRED",
                "message": "Physical retrieval index (Qdrant/vector engine) is deferred to future phase.",
                "candidates": []
            }
        ]
