import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from core.interfaces.module import DatabaseInterface
from core.interfaces.storage import IKnowledgeRecordRepository
from modules.knowledge_base.storage.exceptions import (
    RecordNotFoundError,
    StorageError,
)

class CanonicalKnowledgeRepository(IKnowledgeRecordRepository):
    """Canonical record repository bridging C.2 to EarthMind DatabaseInterface."""

    def __init__(self, db_service: DatabaseInterface):
        if not db_service:
            raise StorageError("DatabaseInterface instance is required for CanonicalKnowledgeRepository.")
        self.db = db_service

    def initialize_schema(self) -> None:
        """Initialize the canonical knowledge records table schema."""
        query = """
        CREATE TABLE IF NOT EXISTS kb_canonical_records (
            record_type TEXT NOT NULL,
            record_id TEXT NOT NULL,
            data_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (record_type, record_id)
        );
        """
        try:
            self.db.execute(query)
        except Exception as e:
            raise StorageError(f"Failed to initialize canonical records schema: {str(e)}")

    def save_record(self, record_type: str, record_id: str, data: Dict[str, Any]) -> str:
        if not record_type or not record_id:
            raise StorageError("Record type and record ID must be non-empty.")

        self.initialize_schema()

        now_iso = datetime.now(timezone.utc).isoformat()
        data_json = json.dumps(data)

        # Check existing
        existing = self.get_record(record_type, record_id)
        if existing:
            query = """
            UPDATE kb_canonical_records
            SET data_json = ?, updated_at = ?
            WHERE record_type = ? AND record_id = ?;
            """
            self.db.execute(query, (data_json, now_iso, record_type, record_id))
        else:
            query = """
            INSERT INTO kb_canonical_records (record_type, record_id, data_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?);
            """
            self.db.execute(query, (record_type, record_id, data_json, now_iso, now_iso))

        return record_id

    def get_record(self, record_type: str, record_id: str) -> Optional[Dict[str, Any]]:
        self.initialize_schema()
        query = """
        SELECT record_type, record_id, data_json, created_at, updated_at
        FROM kb_canonical_records
        WHERE record_type = ? AND record_id = ?;
        """
        row = self.db.fetch_one(query, (record_type, record_id))
        if not row:
            return None

        try:
            record_data = json.loads(row["data_json"])
            record_data["_meta"] = {
                "record_type": row["record_type"],
                "record_id": row["record_id"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            return record_data
        except Exception as e:
            raise StorageError(f"Error parsing json for record '{record_id}': {str(e)}")

    def list_records(
        self,
        record_type: str,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        self.initialize_schema()
        query = """
        SELECT record_type, record_id, data_json, created_at, updated_at
        FROM kb_canonical_records
        WHERE record_type = ?;
        """
        rows = self.db.fetch_all(query, (record_type,))
        results = []
        for row in rows:
            try:
                rec_data = json.loads(row["data_json"])
                rec_data["_meta"] = {
                    "record_type": row["record_type"],
                    "record_id": row["record_id"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }

                # Apply optional filtering
                if filters:
                    match = True
                    for k, v in filters.items():
                        if rec_data.get(k) != v:
                            match = False
                            break
                    if not match:
                        continue
                results.append(rec_data)
            except Exception:
                continue

        return results

    def delete_record(self, record_type: str, record_id: str) -> bool:
        self.initialize_schema()
        existing = self.get_record(record_type, record_id)
        if not existing:
            raise RecordNotFoundError(f"Record '{record_id}' of type '{record_type}' not found.")

        query = """
        DELETE FROM kb_canonical_records
        WHERE record_type = ? AND record_id = ?;
        """
        self.db.execute(query, (record_type, record_id))
        return True
