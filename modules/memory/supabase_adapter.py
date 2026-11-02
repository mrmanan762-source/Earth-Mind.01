"""Supabase PostgreSQL storage adapter implementation of IMemoryStorageAdapter.

Provides production-grade persistent storage for EarthMind Memory records using PostgreSQL,
strictly behind the IMemoryStorageAdapter protocol.
Enforces optimistic locking, UTC timestamp normalization, domain separation,
safe parameterized operations, and transparent error mapping.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional
import psycopg2
import psycopg2.extras
from psycopg2 import sql

from core.interfaces.memory_storage import IMemoryStorageAdapter
from core.schemas.memory import (
    KnowledgeClassification,
    MemoryDomain,
    MemoryRecord,
    MemoryRecordStatus,
    MemoryScope,
    MemorySearchCriteria,
    StorageHealthResult,
)
from modules.database.postgres_db import PostgresDatabaseService
from modules.memory.errors import (
    MemoryConflictError,
    MemoryInvalidArgumentError,
    MemoryNotFoundError,
    MemoryStorageError,
    MemoryStorageUnavailableError,
)


class SupabasePostgresMemoryStorageAdapter(IMemoryStorageAdapter):
    """Production-oriented PostgreSQL / Supabase storage adapter for Memory Module Level 3."""

    provider_name: str = "supabase_postgresql"

    def __init__(
        self,
        db_service: Optional[PostgresDatabaseService] = None,
        table_name: str = "memory_records",
    ):
        self.db = db_service or PostgresDatabaseService()
        self.table_name = table_name

    def _ensure_utc(self, dt: Optional[datetime]) -> Optional[datetime]:
        """Ensure datetime is timezone-aware and set to UTC."""
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def _row_to_record(self, row: Dict[str, Any]) -> MemoryRecord:
        """Map a database row dictionary to an immutable MemoryRecord model."""
        payload_data = row["payload"]
        if isinstance(payload_data, str):
            try:
                payload_data = json.loads(payload_data)
            except Exception:
                pass

        return MemoryRecord(
            record_id=row["record_id"],
            domain=MemoryDomain(row["domain"]),
            record_type=row["record_type"],
            owner_id=row["owner_id"],
            scope_type=MemoryScope(row["scope_type"]),
            scope_id=row["scope_id"],
            payload=payload_data,
            source=row["source"],
            created_at=self._ensure_utc(row["created_at"]),
            updated_at=self._ensure_utc(row["updated_at"]),
            schema_version=row["schema_version"],
            record_version=row["record_version"],
            status=MemoryRecordStatus(row["status"]),
            retention_policy_id=row["retention_policy_id"],
            expires_at=self._ensure_utc(row["expires_at"]),
            classification=KnowledgeClassification(row["classification"]),
            correlation_id=row["correlation_id"],
        )

    def _handle_db_exception(self, exc: Exception, operation: str, record_id: Optional[str] = None) -> None:
        """Translate psycopg2 and database exceptions to approved Memory error hierarchy with secret masking."""
        err_msg = str(exc)
        # Redact any accidental credential leaks from error string
        for secret_kw in ["password", "secret", "token", "key"]:
            if secret_kw in err_msg.lower():
                err_msg = f"{type(exc).__name__}: [sensitive parameters redacted]"
                break

        if isinstance(exc, (psycopg2.OperationalError, psycopg2.DatabaseError)) and (
            "could not connect" in str(exc).lower()
            or "connection refused" in str(exc).lower()
            or "connection timed out" in str(exc).lower()
            or "server closed the connection" in str(exc).lower()
            or "timeout expired" in str(exc).lower()
        ):
            raise MemoryStorageUnavailableError(
                self.provider_name,
                f"PostgreSQL storage unavailable during {operation}: {err_msg}",
            ) from exc

        if isinstance(exc, psycopg2.IntegrityError):
            pgcode = getattr(exc, "pgcode", "")
            # 23505 = unique_violation
            if pgcode == "23505" or "unique constraint" in str(exc).lower():
                raise MemoryConflictError(
                    record_id=record_id or "unknown",
                    details=f"Record '{record_id}' already exists in storage.",
                    operation=operation,
                ) from exc
            # 23514 = check_violation
            if pgcode == "23514" or "check constraint" in str(exc).lower():
                raise MemoryInvalidArgumentError(
                    f"PostgreSQL check constraint violation during {operation}: {err_msg}",
                    operation=operation,
                ) from exc

        raise MemoryStorageError(
            self.provider_name,
            f"Database error during {operation}: {err_msg}",
        ) from exc

    def store_record(self, record: MemoryRecord) -> MemoryRecord:
        """Store a new memory record in PostgreSQL.

        Raises:
            MemoryConflictError: If a record with the same record_id already exists.
            MemoryStorageUnavailableError: If database is unreachable.
            MemoryStorageError: On database failure.
        """
        created_at_utc = self._ensure_utc(record.created_at)
        updated_at_utc = self._ensure_utc(record.updated_at)
        expires_at_utc = self._ensure_utc(record.expires_at)

        insert_sql = sql.SQL("""
            INSERT INTO {} (
                record_id, domain, record_type, owner_id, scope_type, scope_id,
                payload, source, created_at, updated_at, schema_version,
                record_version, status, retention_policy_id, expires_at,
                classification, correlation_id
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s
            ) RETURNING *;
        """).format(sql.Identifier(self.table_name))

        params = (
            record.record_id,
            record.domain.value,
            record.record_type,
            record.owner_id,
            record.scope_type.value,
            record.scope_id,
            json.dumps(record.payload),
            record.source,
            created_at_utc,
            updated_at_utc,
            record.schema_version,
            record.record_version,
            record.status.value,
            record.retention_policy_id,
            expires_at_utc,
            record.classification.value,
            record.correlation_id,
        )

        try:
            conn = self.db.get_connection()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                    cursor.execute(insert_sql, params)
                    row = cursor.fetchone()
                    conn.commit()
                    return self._row_to_record(row)
            except Exception:
                conn.rollback()
                raise
            finally:
                self.db.put_connection(conn)
        except Exception as exc:
            self._handle_db_exception(exc, operation="store_record", record_id=record.record_id)

    def get_record(self, record_id: str) -> Optional[MemoryRecord]:
        """Retrieve a single memory record by its immutable record_id."""
        query_sql = sql.SQL("SELECT * FROM {} WHERE record_id = %s;").format(sql.Identifier(self.table_name))

        try:
            conn = self.db.get_connection()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                    cursor.execute(query_sql, (record_id,))
                    row = cursor.fetchone()
                    if row is None:
                        return None
                    return self._row_to_record(row)
            finally:
                self.db.put_connection(conn)
        except Exception as exc:
            self._handle_db_exception(exc, operation="get_record", record_id=record_id)

    def search_records(self, criteria: MemorySearchCriteria) -> List[MemoryRecord]:
        """Search memory records using structured criteria."""
        clauses = []
        params: List[Any] = []

        if criteria.domain:
            clauses.append("domain = %s")
            params.append(criteria.domain.value)

        if criteria.owner_id is not None:
            clauses.append("owner_id = %s")
            params.append(criteria.owner_id)

        if criteria.scope_type:
            clauses.append("scope_type = %s")
            params.append(criteria.scope_type.value)

        if criteria.scope_id:
            clauses.append("scope_id = %s")
            params.append(criteria.scope_id)

        if criteria.record_type:
            clauses.append("record_type = %s")
            params.append(criteria.record_type)

        if criteria.status:
            clauses.append("status = %s")
            params.append(criteria.status.value)

        if criteria.classification:
            clauses.append("classification = %s")
            params.append(criteria.classification.value)

        if criteria.correlation_id:
            clauses.append("correlation_id = %s")
            params.append(criteria.correlation_id)

        if not criteria.include_expired:
            clauses.append("(expires_at IS NULL OR expires_at > %s)")
            params.append(datetime.now(timezone.utc))

        where_expr = " AND ".join(clauses) if clauses else "TRUE"

        # Deterministic sorting matching criteria
        sort_column = "created_at"
        if getattr(criteria, "sort_by", None):
            sort_val = criteria.sort_by.value if hasattr(criteria.sort_by, "value") else str(criteria.sort_by)
            if sort_val in ("created_at", "updated_at", "record_id"):
                sort_column = sort_val

        sort_dir = "DESC"
        if getattr(criteria, "sort_order", None):
            order_val = criteria.sort_order.value if hasattr(criteria.sort_order, "value") else str(criteria.sort_order)
            if order_val.upper() in ("ASC", "DESC"):
                sort_dir = order_val.upper()

        query_str = f"SELECT * FROM {{}} WHERE {where_expr} ORDER BY {{}} {sort_dir} LIMIT %s OFFSET %s;"
        params.extend([criteria.limit, criteria.offset])

        query_sql = sql.SQL(query_str).format(sql.Identifier(self.table_name), sql.Identifier(sort_column))

        try:
            conn = self.db.get_connection()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                    cursor.execute(query_sql, tuple(params))
                    rows = cursor.fetchall()
                    return [self._row_to_record(r) for r in rows]
            finally:
                self.db.put_connection(conn)
        except Exception as exc:
            self._handle_db_exception(exc, operation="search_records")

    def update_record(
        self,
        record: MemoryRecord,
        expected_version: Optional[int] = None,
    ) -> MemoryRecord:
        """Update an existing memory record with optimistic concurrency control."""
        # 1. Fetch current version to evaluate existence vs version conflict
        query_sql = sql.SQL("SELECT record_version FROM {} WHERE record_id = %s;").format(
            sql.Identifier(self.table_name)
        )

        try:
            conn = self.db.get_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(query_sql, (record.record_id,))
                    row = cursor.fetchone()
                    if row is None:
                        raise MemoryNotFoundError(record.record_id, operation="update_record")
                    stored_version = row[0]

                if expected_version is not None and stored_version != expected_version:
                    raise MemoryConflictError(
                        record.record_id,
                        f"Version mismatch: expected {expected_version}, found {stored_version}.",
                        operation="update_record",
                    )

                # Execute update
                updated_at_utc = self._ensure_utc(record.updated_at) or datetime.now(timezone.utc)
                expires_at_utc = self._ensure_utc(record.expires_at)

                if expected_version is not None:
                    update_sql = sql.SQL("""
                        UPDATE {} SET
                            domain = %s,
                            record_type = %s,
                            owner_id = %s,
                            scope_type = %s,
                            scope_id = %s,
                            payload = %s,
                            source = %s,
                            updated_at = %s,
                            schema_version = %s,
                            record_version = %s,
                            status = %s,
                            retention_policy_id = %s,
                            expires_at = %s,
                            classification = %s,
                            correlation_id = %s
                        WHERE record_id = %s AND record_version = %s
                        RETURNING *;
                    """).format(sql.Identifier(self.table_name))
                    params = (
                        record.domain.value,
                        record.record_type,
                        record.owner_id,
                        record.scope_type.value,
                        record.scope_id,
                        json.dumps(record.payload),
                        record.source,
                        updated_at_utc,
                        record.schema_version,
                        record.record_version,
                        record.status.value,
                        record.retention_policy_id,
                        expires_at_utc,
                        record.classification.value,
                        record.correlation_id,
                        record.record_id,
                        expected_version,
                    )
                else:
                    update_sql = sql.SQL("""
                        UPDATE {} SET
                            domain = %s,
                            record_type = %s,
                            owner_id = %s,
                            scope_type = %s,
                            scope_id = %s,
                            payload = %s,
                            source = %s,
                            updated_at = %s,
                            schema_version = %s,
                            record_version = %s,
                            status = %s,
                            retention_policy_id = %s,
                            expires_at = %s,
                            classification = %s,
                            correlation_id = %s
                        WHERE record_id = %s
                        RETURNING *;
                    """).format(sql.Identifier(self.table_name))
                    params = (
                        record.domain.value,
                        record.record_type,
                        record.owner_id,
                        record.scope_type.value,
                        record.scope_id,
                        json.dumps(record.payload),
                        record.source,
                        updated_at_utc,
                        record.schema_version,
                        record.record_version,
                        record.status.value,
                        record.retention_policy_id,
                        expires_at_utc,
                        record.classification.value,
                        record.correlation_id,
                        record.record_id,
                    )

                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                    cursor.execute(update_sql, params)
                    updated_row = cursor.fetchone()
                    if updated_row is None:
                        # Another concurrent update modified the version in between
                        raise MemoryConflictError(
                            record.record_id,
                            "Concurrent update detected: record was modified by another operation.",
                            operation="update_record",
                        )
                    conn.commit()
                    return self._row_to_record(updated_row)
            except Exception:
                conn.rollback()
                raise
            finally:
                self.db.put_connection(conn)
        except (MemoryNotFoundError, MemoryConflictError):
            raise
        except Exception as exc:
            self._handle_db_exception(exc, operation="update_record", record_id=record.record_id)

    def delete_record(self, record_id: str, soft: bool = True) -> bool:
        """Delete a memory record by record_id."""
        if soft:
            query_sql = sql.SQL("""
                UPDATE {} SET status = %s, updated_at = %s
                WHERE record_id = %s;
            """).format(sql.Identifier(self.table_name))
            params = (MemoryRecordStatus.DELETED.value, datetime.now(timezone.utc), record_id)
        else:
            query_sql = sql.SQL("DELETE FROM {} WHERE record_id = %s;").format(sql.Identifier(self.table_name))
            params = (record_id,)

        try:
            conn = self.db.get_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(query_sql, params)
                    deleted = cursor.rowcount > 0
                    conn.commit()
                    return deleted
            except Exception:
                conn.rollback()
                raise
            finally:
                self.db.put_connection(conn)
        except Exception as exc:
            self._handle_db_exception(exc, operation="delete_record", record_id=record_id)

    def get_record_metadata(self, record_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve record metadata projection without loading the JSONB payload."""
        meta_sql = sql.SQL("""
            SELECT record_id, domain, record_type, owner_id, scope_type, scope_id,
                   created_at, updated_at, schema_version, record_version, status,
                   classification, correlation_id
            FROM {} WHERE record_id = %s;
        """).format(sql.Identifier(self.table_name))

        try:
            conn = self.db.get_connection()
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                    cursor.execute(meta_sql, (record_id,))
                    row = cursor.fetchone()
                    if row is None:
                        return None
                    return {
                        "record_id": row["record_id"],
                        "domain": row["domain"],
                        "record_type": row["record_type"],
                        "owner_id": row["owner_id"],
                        "scope_type": row["scope_type"],
                        "scope_id": row["scope_id"],
                        "created_at": self._ensure_utc(row["created_at"]).isoformat(),
                        "updated_at": self._ensure_utc(row["updated_at"]).isoformat(),
                        "schema_version": row["schema_version"],
                        "record_version": row["record_version"],
                        "status": row["status"],
                        "classification": row["classification"],
                        "correlation_id": row["correlation_id"],
                    }
            finally:
                self.db.put_connection(conn)
        except Exception as exc:
            self._handle_db_exception(exc, operation="get_record_metadata", record_id=record_id)

    def check_health(self) -> StorageHealthResult:
        """Evaluate connectivity and operational capability of PostgreSQL."""
        try:
            conn = self.db.get_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1;")
                    cursor.fetchone()

                    # Query table count
                    count_sql = sql.SQL("SELECT count(*) FROM {};").format(sql.Identifier(self.table_name))
                    cursor.execute(count_sql)
                    count = cursor.fetchone()[0]

                    return StorageHealthResult(
                        is_healthy=True,
                        provider_name=self.provider_name,
                        details={"record_count": count, "table": self.table_name},
                    )
            finally:
                self.db.put_connection(conn)
        except Exception as exc:
            return StorageHealthResult(
                is_healthy=False,
                provider_name=self.provider_name,
                details={"error": type(exc).__name__},
            )
