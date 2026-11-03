"""PostgreSQL implementation of DatabaseInterface for the EarthMind Database Module.

Provides robust connection management, safe parameterized query execution,
and resource cleanup for PostgreSQL / Supabase PostgreSQL instances.
"""

from typing import Any, Dict, List, Optional
import psycopg2
import psycopg2.extras
from psycopg2 import pool

from core.interfaces.module import DatabaseInterface
from core.config.settings import PostgresConfig
from core.logging.logger import get_logger

logger = get_logger("modules.database.postgres")


class PostgresDatabaseService(DatabaseInterface):
    """PostgreSQL implementation of DatabaseInterface using connection pooling."""

    def __init__(self, config: Optional[PostgresConfig] = None):
        self.config = config or PostgresConfig()
        self._pool: Optional[pool.SimpleConnectionPool] = None

    def connect(self) -> None:
        """Initialize connection pool to PostgreSQL."""
        if self._pool is None:
            try:
                conn_kwargs: Dict[str, Any] = {
                    "connect_timeout": int(self.config.connect_timeout),
                    "options": f"-c statement_timeout={self.config.statement_timeout_ms}",
                }

                if self.config.url:
                    # Normalize URL to encode unencoded special characters in password
                    dsn = self._normalize_dsn(self.config.url)
                    self._pool = pool.SimpleConnectionPool(
                        minconn=self.config.min_pool_size,
                        maxconn=self.config.max_pool_size,
                        dsn=dsn,
                        **conn_kwargs,
                    )
                else:
                    self._pool = pool.SimpleConnectionPool(
                        minconn=self.config.min_pool_size,
                        maxconn=self.config.max_pool_size,
                        host=self.config.host,
                        port=self.config.port,
                        user=self.config.user,
                        password=self.config.password,
                        dbname=self.config.database,
                        sslmode=self.config.sslmode,
                        **conn_kwargs,
                    )
                logger.info("Connected to PostgreSQL database pool.")
            except Exception as e:
                # Never log raw credentials
                logger.error(f"Failed to connect to PostgreSQL: {type(e).__name__}")
                raise

    @staticmethod
    def _normalize_dsn(dsn_url: str) -> str:
        """Ensure password containing special unencoded characters like '@' or '#' is properly handled."""
        import re
        from urllib.parse import quote_plus
        # Match pattern: scheme://user:password@host...
        pattern = r"^(?P<scheme>[^:]+://)(?P<user>[^:]+):(?P<password>.+?)@(?P<host_and_rest>[^@]+)$"
        match = re.match(pattern, dsn_url)
        if match:
            pwd = match.group("password")
            # If '@' or '#' is present unencoded in the password
            if "@" in pwd or "#" in pwd:
                encoded_pwd = quote_plus(pwd)
                return f"{match.group('scheme')}{match.group('user')}:{encoded_pwd}@{match.group('host_and_rest')}"
        return dsn_url

    def disconnect(self) -> None:
        """Close all connections in the pool."""
        if self._pool:
            try:
                self._pool.closeall()
            finally:
                self._pool = None
                logger.info("Disconnected from PostgreSQL database pool.")

    def get_connection(self):
        """Borrow a connection from the pool."""
        if self._pool is None:
            self.connect()
        return self._pool.getconn()

    def put_connection(self, conn, close: bool = False):
        """Return a borrowed connection to the pool."""
        if self._pool and conn:
            self._pool.putconn(conn, close=close)

    def execute(self, query: str, params: tuple = ()) -> Any:
        """Execute a write statement (INSERT/UPDATE/DELETE) with auto-commit."""
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                conn.commit()
                try:
                    return cursor.fetchone()[0]
                except Exception:
                    return cursor.rowcount
        except Exception:
            conn.rollback()
            raise
        finally:
            self.put_connection(conn)

    def fetch_all(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Execute a read query and return all matching records as dictionaries."""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        finally:
            self.put_connection(conn)

    def fetch_one(self, query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """Execute a read query and return a single record as a dictionary."""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
                return dict(row) if row else None
        finally:
            self.put_connection(conn)
