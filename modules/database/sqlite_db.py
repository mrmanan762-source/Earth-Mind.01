import sqlite3
from typing import List, Dict, Any, Optional
from core.interfaces.module import DatabaseInterface
from core.logging.logger import get_logger

logger = get_logger("modules.database.sqlite")

class SQLiteDatabaseService(DatabaseInterface):
    """SQLite implementation of DatabaseInterface."""

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._connection: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        if self._connection is None:
            self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
            self._connection.row_factory = sqlite3.Row
            logger.info(f"Connected to SQLite database at {self.db_path}")

    def disconnect(self) -> None:
        if self._connection:
            self._connection.close()
            self._connection = None
            logger.info("Disconnected from SQLite database.")

    def execute(self, query: str, params: tuple = ()) -> Any:
        if not self._connection:
            self.connect()
        cursor = self._connection.cursor()
        cursor.execute(query, params)
        self._connection.commit()
        return cursor.lastrowid

    def fetch_all(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        if not self._connection:
            self.connect()
        cursor = self._connection.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def fetch_one(self, query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        if not self._connection:
            self.connect()
        cursor = self._connection.cursor()
        cursor.execute(query, params)
        row = cursor.fetchone()
        return dict(row) if row else None
