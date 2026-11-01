"""Memory Module Level 2 Security Schemas and Audit Contracts.

Defines schemas and enums for centralized security enforcement, domain separation,
scope boundaries, and security audit events.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SecurityDecision(str, Enum):
    """Outcome of an authorization evaluation."""
    ALLOW = "ALLOW"
    DENY = "DENY"


class SecurityAuditAction(str, Enum):
    """Action categories for memory security auditing."""
    ACCESS_ALLOWED = "ACCESS_ALLOWED"
    ACCESS_DENIED = "ACCESS_DENIED"
    CROSS_USER_ATTEMPT = "CROSS_USER_ATTEMPT"
    INVALID_DOMAIN_SCOPE = "INVALID_DOMAIN_SCOPE"
    UNAUTHORIZED_GENERAL_WRITE = "UNAUTHORIZED_GENERAL_WRITE"
    INVALID_OR_MISSING_AUTH_CONTEXT = "INVALID_OR_MISSING_AUTH_CONTEXT"
    PRIVATE_TO_GENERAL_PROMOTION_BLOCKED = "PRIVATE_TO_GENERAL_PROMOTION_BLOCKED"


class MemorySecurityAuditEvent(BaseModel):
    """Audit event capturing authorization and access control evaluations.

    CRITICAL SECURITY GUARANTEE:
    This event must NEVER contain sensitive payload content, passwords, tokens,
    or private record body data. It only captures correlation metadata,
    principal identity, target domain/scope, operation type, decision, and reason.
    """
    event_id: str = Field(..., description="Unique identifier for the audit event")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timezone-aware UTC timestamp of the audit event"
    )
    action: SecurityAuditAction = Field(..., description="Classification category of the security event")
    decision: SecurityDecision = Field(..., description="Decision reached (ALLOW or DENY)")
    principal_id: Optional[str] = Field(None, description="Identifier of acting principal, if present")
    owner_id: Optional[str] = Field(None, description="Record owner or claimed owner identifier")
    domain: Optional[str] = Field(None, description="Memory domain evaluated (USER or GENERAL)")
    scope_type: Optional[str] = Field(None, description="Scope type evaluated")
    scope_id: Optional[str] = Field(None, description="Scope identifier evaluated")
    record_id: Optional[str] = Field(None, description="Target record identifier, if applicable")
    operation: str = Field(..., description="Memory operation being evaluated (e.g. CREATE, READ, UPDATE, DELETE, SEARCH)")
    reason: str = Field(..., description="Reasoning or rule explanation for the decision")
    correlation_id: Optional[str] = Field(None, description="Traceability / request correlation identifier")
    client_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Safe, non-sensitive audit metadata (no payload or secret data permitted)"
    )
