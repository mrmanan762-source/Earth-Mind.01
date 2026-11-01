"""Top-level EarthMind Memory Module namespace and API exports."""

from core.schemas.memory import (
    AuthorizationContext,
    KnowledgeClassification,
    MemoryDomain,
    MemoryErrorCode,
    MemoryOperation,
    MemoryRecord,
    MemoryRecordStatus,
    MemoryScope,
    MemorySearchCriteria,
    MemorySortField,
    PayloadSchemaRegistry,
    PrincipalType,
    PurgeCriteria,
    PurgeResult,
    RetentionCategory,
    RetentionPolicy,
    SortOrder,
    StorageHealthResult,
)
from core.interfaces.memory_storage import IMemoryStorageAdapter
from modules.memory.storage_adapter import InMemoryMemoryStorageAdapter
from modules.memory.supabase_adapter import SupabasePostgresMemoryStorageAdapter
from modules.memory.errors import (
    MemoryError,
    MemoryInvalidArgumentError,
    MemoryInvalidRecordSchemaError,
    MemoryUnauthorizedError,
    MemoryForbiddenError,
    MemoryNotFoundError,
    MemoryConflictError,
    MemoryStorageUnavailableError,
    MemoryStorageError,
    MemoryRetentionPolicyViolationError,
    MemoryIntegrityError,
    MemoryInternalError,
)
from modules.memory.security import (
    MemorySecurityAuditor,
    MemorySecurityEnforcer,
)
from modules.memory.memory_service import MemoryService
from modules.memory.memory_validator import MemoryRecordValidator, MemoryValidator
from modules.memory.memory_lifecycle import MemoryLifecycleManager, MemoryLifecycle
from modules.memory.memory_retriever import StructuredMemoryRetriever, MemoryRetriever
from core.interfaces.services import MemoryInterface
from modules.memory.memory_module import MemoryModule

__all__ = [
    # Schemas & Contracts
    "MemoryDomain",
    "MemoryScope",
    "MemoryRecordStatus",
    "MemoryErrorCode",
    "MemoryOperation",
    "PrincipalType",
    "MemoryRecord",
    "AuthorizationContext",
    "MemorySearchCriteria",
    "MemorySortField",
    "SortOrder",
    "StorageHealthResult",
    "PayloadSchemaRegistry",
    "RetentionPolicy",
    "RetentionCategory",
    "PurgeCriteria",
    "PurgeResult",
    "IMemoryStorageAdapter",
    "InMemoryMemoryStorageAdapter",
    "SupabasePostgresMemoryStorageAdapter",
    # Level 1 Exceptions
    "MemoryError",
    "MemoryInvalidArgumentError",
    "MemoryInvalidRecordSchemaError",
    "MemoryUnauthorizedError",
    "MemoryForbiddenError",
    "MemoryNotFoundError",
    "MemoryConflictError",
    "MemoryStorageUnavailableError",
    "MemoryStorageError",
    "MemoryRetentionPolicyViolationError",
    "MemoryIntegrityError",
    "MemoryInternalError",
    # Level 2 Security & Service
    "MemorySecurityAuditor",
    "MemorySecurityEnforcer",
    "MemoryService",
    # Level 4 Operations & Lifecycle
    "MemoryRecordValidator",
    "MemoryValidator",
    "MemoryLifecycleManager",
    "MemoryLifecycle",
    "StructuredMemoryRetriever",
    "MemoryRetriever",
    # Legacy Module
    "MemoryInterface",
    "MemoryModule",
]
