"""EarthMind Memory Module.

Provides memory services, record models, storage abstractions, domain security,
and boundary integration conforming to Memory Module Architecture Specification v1.0.
"""

from core.interfaces.services import MemoryInterface
from modules.memory.memory_module import MemoryModule
from modules.memory.memory_service import MemoryService
from modules.memory.memory_retriever import MemoryRetriever
from modules.memory.memory_lifecycle import MemoryLifecycle
from modules.memory.memory_validator import MemoryValidator
from modules.memory.memory_extractor import MemoryExtractor
from modules.memory.memory_ranker import MemoryRanker

# Level 1 Foundation & Contracts
from core.schemas.memory import (
    MemoryDomain,
    MemoryScope,
    MemoryRecordStatus,
    MemoryErrorCode,
    MemoryOperation,
    MemoryRecord,
    AuthorizationContext,
    MemorySearchCriteria,
    StorageHealthResult,
)
from core.interfaces.memory_storage import IMemoryStorageAdapter
from modules.memory.storage_adapter import InMemoryMemoryStorageAdapter
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

# Level 2 Security & Domains
from core.schemas.memory_security import (
    SecurityDecision,
    SecurityAuditAction,
    MemorySecurityAuditEvent,
)
from modules.memory.security import (
    MemorySecurityAuditor,
    MemorySecurityEnforcer,
)

__all__ = [
    # Legacy interfaces & components
    "MemoryInterface",
    "MemoryModule",
    "MemoryService",
    "MemoryRetriever",
    "MemoryLifecycle",
    "MemoryValidator",
    "MemoryExtractor",
    "MemoryRanker",
    # Level 1 Contracts
    "MemoryDomain",
    "MemoryScope",
    "MemoryRecordStatus",
    "MemoryErrorCode",
    "MemoryOperation",
    "MemoryRecord",
    "AuthorizationContext",
    "MemorySearchCriteria",
    "StorageHealthResult",
    "IMemoryStorageAdapter",
    "InMemoryMemoryStorageAdapter",
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
    # Level 2 Security & Domains
    "SecurityDecision",
    "SecurityAuditAction",
    "MemorySecurityAuditEvent",
    "MemorySecurityAuditor",
    "MemorySecurityEnforcer",
]
