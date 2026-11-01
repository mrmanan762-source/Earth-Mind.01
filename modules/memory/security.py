"""Centralized Security and Governance Enforcement for Memory Module Level 2.

Implements:
1. MemorySecurityAuditor: Safe audit logging with strict payload omission and redacting.
2. MemorySecurityEnforcer: Centralized, fail-closed policy enforcement for:
   - Domain separation (USER vs GENERAL)
   - User ownership enforcement (strict owner match, cross-user denial)
   - Scope-aware access enforcement (USER, CONVERSATION, FARM, FIELD, CROP_CYCLE, GENERAL)
   - General Memory governance (explicit authorization for writes, ordinary user block)
   - Anti-promotion guard (preventing private user data from entering General Memory)
   - Principle of least privilege (no blanket admin/system bypass)
"""

import uuid
from typing import Any, Dict, List, Optional
from core.logging.logger import get_logger
from core.schemas.memory import (
    AuthorizationContext,
    MemoryDomain,
    MemoryOperation,
    MemoryRecord,
    MemoryScope,
)
from core.schemas.memory_security import (
    MemorySecurityAuditEvent,
    SecurityAuditAction,
    SecurityDecision,
)
from modules.memory.errors import (
    MemoryForbiddenError,
    MemoryInvalidArgumentError,
    MemoryUnauthorizedError,
)

logger = get_logger("modules.memory.security")


class MemorySecurityAuditor:
    """Safe, non-intrusive security auditor emitting sanitized audit events."""

    def __init__(self):
        self._audit_log: List[MemorySecurityAuditEvent] = []

    @property
    def audit_events(self) -> List[MemorySecurityAuditEvent]:
        """Return list of recorded audit events."""
        return list(self._audit_log)

    def clear(self) -> None:
        """Clear recorded audit events (useful for test resets)."""
        self._audit_log.clear()

    def record_event(
        self,
        action: SecurityAuditAction,
        decision: SecurityDecision,
        operation: str,
        reason: str,
        principal_id: Optional[str] = None,
        owner_id: Optional[str] = None,
        domain: Optional[str] = None,
        scope_type: Optional[str] = None,
        scope_id: Optional[str] = None,
        record_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        client_metadata: Optional[Dict[str, Any]] = None,
    ) -> MemorySecurityAuditEvent:
        """Record and log a sanitized security audit event."""
        # Sanitize metadata to never include sensitive keys like payload, secret, token, key
        safe_metadata: Dict[str, Any] = {}
        if client_metadata:
            forbidden_keys = {"payload", "secret", "token", "password", "credential", "auth_token"}
            for k, v in client_metadata.items():
                if k.lower() in forbidden_keys:
                    safe_metadata[k] = "[REDACTED]"
                elif isinstance(v, (str, int, float, bool)):
                    safe_metadata[k] = v
                else:
                    safe_metadata[k] = f"<{type(v).__name__}>"

        event = MemorySecurityAuditEvent(
            event_id=f"audit_{uuid.uuid4().hex[:16]}",
            action=action,
            decision=decision,
            principal_id=principal_id,
            owner_id=owner_id,
            domain=domain,
            scope_type=scope_type,
            scope_id=scope_id,
            record_id=record_id,
            operation=operation,
            reason=reason,
            correlation_id=correlation_id,
            client_metadata=safe_metadata,
        )
        self._audit_log.append(event)

        # Log at appropriate level without sensitive details
        log_msg = (
            f"[MEMORY_SECURITY_AUDIT] action={event.action.value} "
            f"decision={event.decision.value} op={event.operation} "
            f"principal={event.principal_id} domain={event.domain} "
            f"scope={event.scope_type}:{event.scope_id} record={event.record_id} "
            f"reason={event.reason}"
        )
        if decision == SecurityDecision.ALLOW:
            logger.info(log_msg)
        else:
            logger.warning(log_msg)

        return event


class MemorySecurityEnforcer:
    """Centralized, fail-closed security enforcer for Memory Module Level 2."""

    # Approved roles/permissions that allow writing to General Memory
    APPROVED_GENERAL_WRITE_ROLES = {"curator", "knowledge_admin", "general_memory_manager"}

    def __init__(self, auditor: Optional[MemorySecurityAuditor] = None):
        self.auditor = auditor or MemorySecurityAuditor()

    def enforce_authorization(
        self,
        context: Optional[AuthorizationContext],
        operation: MemoryOperation,
        domain: MemoryDomain,
        scope_type: MemoryScope,
        scope_id: Optional[str] = None,
        owner_id: Optional[str] = None,
        record_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        record: Optional[MemoryRecord] = None,
    ) -> None:
        """Central gate enforcing domain, scope, ownership, and governance rules.

        Raises:
            MemoryUnauthorizedError: If identity context is missing, invalid, or anonymous.
            MemoryForbiddenError: If principal lacks permission, tries cross-user access, or violates governance.
            MemoryInvalidArgumentError: If domain or scope combinations are invalid.
        """
        op_name = operation.value

        # 1. Missing or invalid AuthorizationContext -> Fail closed with MemoryUnauthorizedError
        if context is None:
            self.auditor.record_event(
                action=SecurityAuditAction.INVALID_OR_MISSING_AUTH_CONTEXT,
                decision=SecurityDecision.DENY,
                operation=op_name,
                reason="Authorization context is completely missing.",
                domain=domain.value if domain else None,
                scope_type=scope_type.value if scope_type else None,
                scope_id=scope_id,
                record_id=record_id,
                correlation_id=correlation_id,
            )
            raise MemoryUnauthorizedError("Missing authorization context.", operation=op_name)

        if not getattr(context, "principal_id", None) or not context.principal_id.strip():
            self.auditor.record_event(
                action=SecurityAuditAction.INVALID_OR_MISSING_AUTH_CONTEXT,
                decision=SecurityDecision.DENY,
                operation=op_name,
                reason="Principal ID is empty or invalid.",
                domain=domain.value if domain else None,
                scope_type=scope_type.value if scope_type else None,
                scope_id=scope_id,
                record_id=record_id,
                correlation_id=correlation_id,
            )
            raise MemoryUnauthorizedError("Authorization principal_id cannot be empty.", operation=op_name)

        principal = context.principal_id.strip()

        # 2. Domain and Scope Structural Validation
        # Unknown scope or invalid combination
        if not isinstance(domain, MemoryDomain):
            self.auditor.record_event(
                action=SecurityAuditAction.INVALID_DOMAIN_SCOPE,
                decision=SecurityDecision.DENY,
                operation=op_name,
                principal_id=principal,
                reason=f"Unknown or invalid domain: '{domain}'.",
                domain=str(domain),
                scope_type=str(scope_type),
                record_id=record_id,
                correlation_id=correlation_id,
            )
            raise MemoryInvalidArgumentError(f"Invalid domain '{domain}'.", operation=op_name)

        if not isinstance(scope_type, MemoryScope):
            self.auditor.record_event(
                action=SecurityAuditAction.INVALID_DOMAIN_SCOPE,
                decision=SecurityDecision.DENY,
                operation=op_name,
                principal_id=principal,
                reason=f"Unknown or invalid scope: '{scope_type}'.",
                domain=domain.value,
                scope_type=str(scope_type),
                record_id=record_id,
                correlation_id=correlation_id,
            )
            raise MemoryInvalidArgumentError(f"Invalid scope '{scope_type}'.", operation=op_name)

        # USER domain records cannot have GENERAL scope
        if domain == MemoryDomain.USER and scope_type == MemoryScope.GENERAL:
            self.auditor.record_event(
                action=SecurityAuditAction.INVALID_DOMAIN_SCOPE,
                decision=SecurityDecision.DENY,
                operation=op_name,
                principal_id=principal,
                reason="USER domain cannot have GENERAL scope.",
                domain=domain.value,
                scope_type=scope_type.value,
                record_id=record_id,
                correlation_id=correlation_id,
            )
            raise MemoryInvalidArgumentError("USER domain records cannot have GENERAL scope.", operation=op_name)

        # GENERAL domain records cannot have non-GENERAL scopes
        if domain == MemoryDomain.GENERAL and scope_type != MemoryScope.GENERAL:
            self.auditor.record_event(
                action=SecurityAuditAction.INVALID_DOMAIN_SCOPE,
                decision=SecurityDecision.DENY,
                operation=op_name,
                principal_id=principal,
                reason=f"GENERAL domain records cannot have scope '{scope_type.value}'.",
                domain=domain.value,
                scope_type=scope_type.value,
                record_id=record_id,
                correlation_id=correlation_id,
            )
            raise MemoryInvalidArgumentError(f"GENERAL domain records cannot have scope '{scope_type.value}'.", operation=op_name)

        # 3. Anti-Promotion Guard: Private User Memory cannot be stored into General Memory
        if domain == MemoryDomain.GENERAL:
            # General memory records MUST NOT have owner_id
            if owner_id is not None and owner_id.strip():
                self.auditor.record_event(
                    action=SecurityAuditAction.PRIVATE_TO_GENERAL_PROMOTION_BLOCKED,
                    decision=SecurityDecision.DENY,
                    operation=op_name,
                    principal_id=principal,
                    owner_id=owner_id,
                    domain=domain.value,
                    scope_type=scope_type.value,
                    record_id=record_id,
                    reason="GENERAL domain records must not have an owner_id. Private user records cannot be promoted to General Memory.",
                    correlation_id=correlation_id,
                )
                raise MemoryForbiddenError("GENERAL domain records must not have an owner_id. Private user records cannot be promoted.", operation=op_name)

            if record and record.domain == MemoryDomain.USER:
                self.auditor.record_event(
                    action=SecurityAuditAction.PRIVATE_TO_GENERAL_PROMOTION_BLOCKED,
                    decision=SecurityDecision.DENY,
                    operation=op_name,
                    principal_id=principal,
                    owner_id=record.owner_id,
                    domain=domain.value,
                    scope_type=scope_type.value,
                    record_id=record_id,
                    reason="Direct promotion from USER domain record to GENERAL domain is forbidden.",
                    correlation_id=correlation_id,
                )
                raise MemoryForbiddenError("Direct promotion from USER domain to GENERAL domain is forbidden.", operation=op_name)

        # 4. General Memory Governance
        if domain == MemoryDomain.GENERAL:
            # Writes (CREATE, UPDATE, DELETE) require explicit authorization decision / approved role
            if operation in {MemoryOperation.CREATE, MemoryOperation.UPDATE, MemoryOperation.DELETE}:
                is_authorized_writer = False
                # Check explicit roles
                user_roles = set(context.roles or [])
                if user_roles.intersection(self.APPROVED_GENERAL_WRITE_ROLES):
                    is_authorized_writer = True

                # Check policy_context explicit claim
                if context.policy_context.get("allow_general_write") is True:
                    is_authorized_writer = True

                if not is_authorized_writer:
                    self.auditor.record_event(
                        action=SecurityAuditAction.UNAUTHORIZED_GENERAL_WRITE,
                        decision=SecurityDecision.DENY,
                        operation=op_name,
                        principal_id=principal,
                        domain=domain.value,
                        scope_type=scope_type.value,
                        scope_id=scope_id,
                        record_id=record_id,
                        reason=f"Principal '{principal}' is not authorized to modify General Memory. Write requires explicit governance privilege.",
                        correlation_id=correlation_id,
                    )
                    raise MemoryForbiddenError(
                        f"Principal '{principal}' is not authorized to perform '{op_name}' on General Memory.",
                        operation=op_name
                    )

            # General Memory Read / Search is governed: accessible to authenticated subjects
            self.auditor.record_event(
                action=SecurityAuditAction.ACCESS_ALLOWED,
                decision=SecurityDecision.ALLOW,
                operation=op_name,
                principal_id=principal,
                domain=domain.value,
                scope_type=scope_type.value,
                scope_id=scope_id,
                record_id=record_id,
                reason="General Memory operation authorized.",
                correlation_id=correlation_id,
            )
            return

        # 5. User Memory Ownership Enforcement
        # USER domain records MUST have a non-empty owner_id
        effective_owner = owner_id or (record.owner_id if record else None)
        if not effective_owner or not effective_owner.strip():
            self.auditor.record_event(
                action=SecurityAuditAction.ACCESS_DENIED,
                decision=SecurityDecision.DENY,
                operation=op_name,
                principal_id=principal,
                domain=domain.value,
                scope_type=scope_type.value,
                scope_id=scope_id,
                record_id=record_id,
                reason="USER domain records must have an owner_id.",
                correlation_id=correlation_id,
            )
            raise MemoryInvalidArgumentError("USER domain records must have a non-empty owner_id.", operation=op_name)

        # Check ownership match against context
        # A principal can access records where:
        # - principal_id == owner_id, OR
        # - context.owner_id == owner_id (acting on behalf of owner with verified claim)
        # Note: No blanket admin/system bypass. Least privilege is applied.
        # Role "admin" or "system" must still have explicit permission for the requested operation
        # or must match the owner identity, and cannot bypass cross-user boundaries without explicit delegation.
        has_owner_match = (principal == effective_owner) or (context.owner_id == effective_owner)

        if not has_owner_match:
            # Check if delegated access is explicitly granted in policy_context
            delegated_owners = context.policy_context.get("authorized_owners", [])
            if effective_owner not in delegated_owners:
                self.auditor.record_event(
                    action=SecurityAuditAction.CROSS_USER_ATTEMPT,
                    decision=SecurityDecision.DENY,
                    operation=op_name,
                    principal_id=principal,
                    owner_id=effective_owner,
                    domain=domain.value,
                    scope_type=scope_type.value,
                    scope_id=scope_id,
                    record_id=record_id,
                    reason=f"Cross-user access denied. Principal '{principal}' cannot access records owned by '{effective_owner}'.",
                    correlation_id=correlation_id,
                )
                raise MemoryForbiddenError(
                    f"Access denied: Principal '{principal}' is not authorized to access records owned by '{effective_owner}'.",
                    operation=op_name
                )

        # 6. Scope-Aware Access Enforcement
        # A valid owner does not automatically authorize access to all scopes without verification.
        # Check scope boundaries:
        if scope_id:
            # For USER scope: scope_id should match owner_id or principal
            if scope_type == MemoryScope.USER:
                if scope_id != effective_owner and scope_id != principal:
                    self.auditor.record_event(
                        action=SecurityAuditAction.ACCESS_DENIED,
                        decision=SecurityDecision.DENY,
                        operation=op_name,
                        principal_id=principal,
                        owner_id=effective_owner,
                        domain=domain.value,
                        scope_type=scope_type.value,
                        scope_id=scope_id,
                        record_id=record_id,
                        reason=f"USER scope_id '{scope_id}' does not match owner '{effective_owner}'.",
                        correlation_id=correlation_id,
                    )
                    raise MemoryForbiddenError(
                        f"Scope boundary violation: USER scope_id '{scope_id}' does not match owner '{effective_owner}'.",
                        operation=op_name
                    )

            # For CONVERSATION, FARM, FIELD, CROP_CYCLE scopes:
            # Check if scope is granted in accessible_scopes
            elif scope_type in {
                MemoryScope.CONVERSATION,
                MemoryScope.FARM,
                MemoryScope.FIELD,
                MemoryScope.CROP_CYCLE,
            }:
                allowed_ids = context.accessible_scopes.get(scope_type.value)
                # If accessible_scopes contains "*" or the specific scope_id, access is permitted.
                # If accessible_scopes is not defined for this scope, or scope_id not in allowed list,
                # access must fail closed. Client-provided scope_id is not proof of permission.
                if allowed_ids is None or (scope_id not in allowed_ids and "*" not in allowed_ids):
                    self.auditor.record_event(
                        action=SecurityAuditAction.ACCESS_DENIED,
                        decision=SecurityDecision.DENY,
                        operation=op_name,
                        principal_id=principal,
                        owner_id=effective_owner,
                        domain=domain.value,
                        scope_type=scope_type.value,
                        scope_id=scope_id,
                        record_id=record_id,
                        reason=f"Principal '{principal}' is not authorized for {scope_type.value} scope '{scope_id}'.",
                        correlation_id=correlation_id,
                    )
                    raise MemoryForbiddenError(
                        f"Access denied to scope '{scope_type.value}:{scope_id}'.",
                        operation=op_name
                    )

        # 7. Access Allowed
        self.auditor.record_event(
            action=SecurityAuditAction.ACCESS_ALLOWED,
            decision=SecurityDecision.ALLOW,
            operation=op_name,
            principal_id=principal,
            owner_id=effective_owner,
            domain=domain.value,
            scope_type=scope_type.value,
            scope_id=scope_id,
            record_id=record_id,
            reason="User memory authorization granted.",
            correlation_id=correlation_id,
        )
