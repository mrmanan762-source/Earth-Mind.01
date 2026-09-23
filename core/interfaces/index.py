"""Generic IKnowledgeIndexAdapter Interface for EarthMind C.2 Knowledge Base Index Layer."""

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class IKnowledgeIndexAdapter(Protocol):
    """Generic, provider-agnostic interface for physical/derived index persistence and management."""

    def create_collection(
        self, collection_name: str, config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Create a new index collection/structure."""
        ...

    def ensure_collection_exists(
        self, collection_name: str, dense_dim: int, config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Ensure an index collection exists with required parameters (e.g. vector dimension)."""
        ...

    def index_record(self, collection_name: str, record: Any) -> Any:
        """Index a single IndexRecord into the specified collection."""
        ...

    def index_batch(self, collection_name: str, records: List[Any]) -> Any:
        """Index a batch of IndexRecords into the specified collection, returning an IndexBatchResult."""
        ...

    def update_record(self, collection_name: str, record: Any) -> Any:
        """Update an existing IndexRecord in the specified collection."""
        ...

    def delete_record(self, collection_name: str, record_id: str) -> bool:
        """Delete an index record from the specified collection by record_id."""
        ...

    def get_record(self, collection_name: str, record_id: str) -> Optional[Any]:
        """Retrieve an index record from the specified collection by record_id."""
        ...

    def get_status(self, collection_name: str) -> Dict[str, Any]:
        """Return status and health metrics for the specified collection."""
        ...

    def health_check(self) -> bool:
        """Return operational health status of the index backend."""
        ...

    def is_available(self) -> bool:
        """Return availability status of the index backend."""
        ...
