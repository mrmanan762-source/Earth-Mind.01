"""Canonical Embedding Repository Foundation for C.2 Knowledge Base.

Defines IEmbeddingRepository interface and CanonicalEmbeddingRepository implementation
for persisting derived EmbeddingRecord objects without database or Qdrant lock-in.

Guarantees:
- Pure storage-independent persistence interface for EmbeddingRecord domain objects
- Multi-key lookup (embedding_id, chunk_id, knowledge_unit_id, version_id)
- Idempotency and status lifecycle awareness ('ACTIVE', 'SUPERSEDED', 'DEPRECATED')
- Separation from Index Layer (Qdrant) and SQLite DB internals
"""

import threading
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from modules.knowledge_base.embedding.record import EmbeddingRecord


class IEmbeddingRepository(ABC):
    """Abstract storage interface for persistent EmbeddingRecord domain objects."""

    @abstractmethod
    def save(self, record: EmbeddingRecord) -> None:
        """Saves or updates a single EmbeddingRecord."""
        ...

    @abstractmethod
    def save_batch(self, records: List[EmbeddingRecord]) -> None:
        """Saves a batch of EmbeddingRecords atomically."""
        ...

    @abstractmethod
    def get_by_id(self, embedding_id: str) -> Optional[EmbeddingRecord]:
        """Retrieves an EmbeddingRecord by its unique embedding_id."""
        ...

    @abstractmethod
    def get_by_chunk_id(self, chunk_id: str) -> List[EmbeddingRecord]:
        """Retrieves all EmbeddingRecords associated with a canonical chunk_id."""
        ...

    @abstractmethod
    def get_by_unit_id(self, knowledge_unit_id: str) -> List[EmbeddingRecord]:
        """Retrieves all EmbeddingRecords associated with a canonical knowledge_unit_id."""
        ...

    @abstractmethod
    def get_by_version_id(self, version_id: str) -> List[EmbeddingRecord]:
        """Retrieves all EmbeddingRecords associated with a canonical version_id."""
        ...

    @abstractmethod
    def list_active(self) -> List[EmbeddingRecord]:
        """Lists all active (status='ACTIVE') EmbeddingRecords."""
        ...

    @abstractmethod
    def count(self) -> int:
        """Returns total count of stored EmbeddingRecords."""
        ...

    @abstractmethod
    def clear(self) -> None:
        """Clears all stored records."""
        ...


class CanonicalEmbeddingRepository(IEmbeddingRepository):
    """In-memory and thread-safe implementation of IEmbeddingRepository."""

    def __init__(self):
        self._lock = threading.RLock()
        self._records: Dict[str, EmbeddingRecord] = {}
        self._chunk_index: Dict[str, List[str]] = {}
        self._unit_index: Dict[str, List[str]] = {}
        self._version_index: Dict[str, List[str]] = {}

    def save(self, record: EmbeddingRecord) -> None:
        if not isinstance(record, EmbeddingRecord):
            raise ValueError("Item to save must be an instance of EmbeddingRecord.")

        with self._lock:
            emb_id = record.embedding_id
            self._records[emb_id] = record

            if record.chunk_id:
                ch_list = self._chunk_index.setdefault(record.chunk_id, [])
                if emb_id not in ch_list:
                    ch_list.append(emb_id)

            if record.knowledge_unit_id:
                ku_list = self._unit_index.setdefault(record.knowledge_unit_id, [])
                if emb_id not in ku_list:
                    ku_list.append(emb_id)

            if record.version_id:
                ver_list = self._version_index.setdefault(record.version_id, [])
                if emb_id not in ver_list:
                    ver_list.append(emb_id)

    def save_batch(self, records: List[EmbeddingRecord]) -> None:
        with self._lock:
            for record in records:
                self.save(record)

    def get_by_id(self, embedding_id: str) -> Optional[EmbeddingRecord]:
        with self._lock:
            return self._records.get(embedding_id)

    def get_by_chunk_id(self, chunk_id: str) -> List[EmbeddingRecord]:
        with self._lock:
            ids = self._chunk_index.get(chunk_id, [])
            return [self._records[eid] for eid in ids if eid in self._records]

    def get_by_unit_id(self, knowledge_unit_id: str) -> List[EmbeddingRecord]:
        with self._lock:
            ids = self._unit_index.get(knowledge_unit_id, [])
            return [self._records[eid] for eid in ids if eid in self._records]

    def get_by_version_id(self, version_id: str) -> List[EmbeddingRecord]:
        with self._lock:
            ids = self._version_index.get(version_id, [])
            return [self._records[eid] for eid in ids if eid in self._records]

    def list_active(self) -> List[EmbeddingRecord]:
        with self._lock:
            return [rec for rec in self._records.values() if rec.status == "ACTIVE"]

    def count(self) -> int:
        with self._lock:
            return len(self._records)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()
            self._chunk_index.clear()
            self._unit_index.clear()
            self._version_index.clear()
