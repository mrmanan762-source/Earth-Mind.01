"""EarthMind Memory Module: Record Validation Component.

Validates memory records against:
- Extensible PayloadSchemaRegistry schemas.
- Immutable identity rules (owner_id, domain, scope_type cannot change across updates).
- UTC timestamp validity and expiration logic.
- Record status transitions.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.schemas.memory import (
    MemoryDomain,
    MemoryRecord,
    MemoryRecordStatus,
    PayloadSchemaRegistry,
)
from modules.memory.errors import (
    MemoryForbiddenError,
    MemoryInvalidArgumentError,
    MemoryInvalidRecordSchemaError,
)


class MemoryValidator:
    """Starter alias preserved for backward compatibility."""
    pass


class MemoryRecordValidator(MemoryValidator):
    """Validates memory records during creation, update, and lifecycle transitions."""

    @staticmethod
    def validate_new_record(record: MemoryRecord) -> None:
        """Validate a new memory record prior to storage insertion."""
        if not isinstance(record, MemoryRecord):
            raise MemoryInvalidArgumentError("Record must be an instance of MemoryRecord.", operation="validate_new_record")

        # Validate payload using registered schemas
        try:
            PayloadSchemaRegistry.validate_payload(record.record_type, record.payload)
        except ValueError as e:
            raise MemoryInvalidRecordSchemaError(
                record_type=record.record_type,
                reason=str(e),
                operation="validate_new_record"
            )

        # Check expiration logic
        if record.expires_at is not None:
            if record.expires_at <= record.created_at:
                raise MemoryInvalidArgumentError(
                    f"expires_at ({record.expires_at.isoformat()}) must be later than created_at ({record.created_at.isoformat()}).",
                    operation="validate_new_record"
                )

    @staticmethod
    def validate_update(existing_record: MemoryRecord, updated_record: MemoryRecord) -> None:
        """Validate an updated record against its previous stored state.

        Enforces that immutable fields (record_id, domain, owner_id, scope_type)
        cannot be modified.
        """
        if not isinstance(existing_record, MemoryRecord) or not isinstance(updated_record, MemoryRecord):
            raise MemoryInvalidArgumentError("Both records must be instances of MemoryRecord.", operation="validate_update")

        if updated_record.record_id != existing_record.record_id:
            raise MemoryForbiddenError("Cannot change record_id of an existing record.", operation="validate_update")

        if updated_record.domain != existing_record.domain:
            raise MemoryForbiddenError("Cannot change domain of an existing record.", operation="validate_update")

        if updated_record.owner_id != existing_record.owner_id:
            raise MemoryForbiddenError("Cannot reassign owner_id of an existing record.", operation="validate_update")

        if updated_record.scope_type != existing_record.scope_type:
            raise MemoryForbiddenError("Cannot change scope_type of an existing record.", operation="validate_update")

        # Validate payload schema
        try:
            PayloadSchemaRegistry.validate_payload(updated_record.record_type, updated_record.payload)
        except ValueError as e:
            raise MemoryInvalidRecordSchemaError(
                record_type=updated_record.record_type,
                reason=str(e),
                operation="validate_update"
            )

        # Check timestamp consistency
        if updated_record.updated_at < existing_record.created_at:
            raise MemoryInvalidArgumentError(
                "updated_at cannot be earlier than created_at.",
                operation="validate_update"
            )

        if updated_record.expires_at is not None:
            if updated_record.expires_at <= existing_record.created_at:
                raise MemoryInvalidArgumentError(
                    "expires_at must be strictly later than created_at.",
                    operation="validate_update"
                )
