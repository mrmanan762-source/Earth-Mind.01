from typing import Protocol, Dict, Any, Optional, List, Union

class IArtifactStorage(Protocol):
    """Interface protocol for raw source artifact storage."""

    def save_artifact(
        self,
        artifact_id: str,
        content: Union[bytes, str],
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Save raw artifact content and metadata."""
        ...

    def get_artifact(self, artifact_id: str) -> bytes:
        """Retrieve raw artifact binary content."""
        ...

    def get_artifact_metadata(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve metadata associated with an artifact."""
        ...

    def has_artifact(self, artifact_id: str) -> bool:
        """Check whether an artifact exists in storage."""
        ...

    def delete_artifact(self, artifact_id: str) -> bool:
        """Delete an artifact and its metadata from storage."""
        ...

    def list_artifacts(self) -> List[str]:
        """List all artifact IDs in storage."""
        ...


class IKnowledgeIndex(Protocol):
    """Interface protocol for derived retrieval index boundaries."""

    def index_status(self) -> Dict[str, Any]:
        """Get index operational status and health metadata."""
        ...

    def register_index_record(self, record: Dict[str, Any]) -> str:
        """Register a logical index record (derived from canonical knowledge)."""
        ...

    def search_placeholder(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Placeholder query method for derived index boundary."""
        ...


class IKnowledgeRecordRepository(Protocol):
    """Interface protocol for canonical structured record repository."""

    def initialize_schema(self) -> None:
        """Initialize database tables for canonical knowledge records."""
        ...

    def save_record(self, record_type: str, record_id: str, data: Dict[str, Any]) -> str:
        """Save a canonical knowledge record."""
        ...

    def get_record(self, record_type: str, record_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a canonical knowledge record by ID."""
        ...

    def list_records(
        self,
        record_type: str,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """List canonical knowledge records of a given type."""
        ...

    def delete_record(self, record_type: str, record_id: str) -> bool:
        """Delete a canonical knowledge record by ID."""
        ...
