"""SQLAlchemy Core persistence helpers for SmartQueue."""

from __future__ import annotations

import hashlib
import hmac
import math
import os
import re
import secrets
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

from sqlalchemy.engine.url import URL, make_url
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    create_engine,
    event,
    inspect,
    text,
)
from sqlalchemy.engine import Connection, Engine, Row
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool


DATABASE_PATH = Path(__file__).resolve().with_name("smartqueue.db")
SERVICE_TYPES = {
    "Certificate",
    "Fee Payment",
    "General Enquiry",
    "Admission",
}
TOKEN_STATUSES = {"Waiting", "Serving", "Served"}
PASSWORD_HASH_ITERATIONS = 600_000
PASSWORD_HASH_ALGORITHM = "sha256"
_POSTGRES_ADMIN_LOCK_ID = 732_114_095_001

_metadata = MetaData()
_admins = Table(
    "admins",
    _metadata,
    Column("admin_id", Integer, primary_key=True),
    Column("username", Text, nullable=False, unique=True),
    Column("password_hash", Text, nullable=False),
    sqlite_autoincrement=True,
)
_service_counters = Table(
    "service_counters",
    _metadata,
    Column("counter_id", Integer, primary_key=True),
    Column("counter_name", Text, nullable=False),
    Column("service_type", Text, nullable=False),
    Column("people_waiting", Integer, server_default=text("0")),
    Column("active_counters", Integer, server_default=text("1")),
    Column("avg_service_time", Float, server_default=text("5")),
    Column("is_active", Integer, server_default=text("1")),
    sqlite_autoincrement=True,
)
_queue_tokens = Table(
    "queue_tokens",
    _metadata,
    Column("token_id", Integer, primary_key=True),
    Column("token_number", Text, nullable=False),
    Column("tracking_reference", Text, nullable=False, unique=True),
    Column("counter_id", Integer, ForeignKey("service_counters.counter_id"), nullable=False),
    Column("visitor_name", Text),
    Column("status", Text, server_default=text("'Waiting'")),
    Column("created_at", DateTime, server_default=text("CURRENT_TIMESTAMP")),
    Column("served_at", DateTime),
    sqlite_autoincrement=True,
)
Index(
    "idx_queue_tokens_counter_number",
    _queue_tokens.c.counter_id,
    _queue_tokens.c.token_number,
    unique=True,
)
_queue_history = Table(
    "queue_history",
    _metadata,
    Column("history_id", Integer, primary_key=True),
    Column("counter_id", Integer),
    Column("people_waiting", Integer),
    Column("actual_waiting_time", Float),
    Column("predicted_waiting_time", Float),
    Column("recorded_at", DateTime, server_default=text("CURRENT_TIMESTAMP")),
    sqlite_autoincrement=True,
)

_engine_lock = threading.Lock()
_engine: Engine | None = None
_engine_key: str | None = None


class DatabaseOperationError(RuntimeError):
    """Raised when a database operation fails."""


@contextmanager
def _connection() -> Generator["_CoreConnection", None, None]:
    """Open a transactional SQLAlchemy connection and always close it."""
    try:
        engine = _get_engine()
        with engine.begin() as connection:
            yield _CoreConnection(connection)
    except SQLAlchemyError as exc:
        raise DatabaseOperationError("Database operation failed.") from exc


class _RowView(Mapping[str, Any]):
    """Expose SQLAlchemy rows with the key and positional access used by legacy helpers."""

    def __init__(self, row: Row[Any]) -> None:
        self._mapping = row._mapping
        self._values = tuple(row)

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            return self._values[key]
        return self._mapping[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._mapping)

    def __len__(self) -> int:
        return len(self._mapping)


class _CoreResult:
    def __init__(self, result: Any) -> None:
        self._result = result

    @property
    def rowcount(self) -> int:
        return self._result.rowcount

    @property
    def lastrowid(self) -> int | None:
        return self._result.lastrowid

    def fetchone(self) -> _RowView | None:
        row = self._result.fetchone()
        return _RowView(row) if row is not None else None

    def fetchall(self) -> list[_RowView]:
        return [_RowView(row) for row in self._result.fetchall()]


class _CoreConnection:
    """Small adapter for the existing SQL helpers over SQLAlchemy Core."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection
        self.dialect = connection.dialect

    @staticmethod
    def _bind_parameters(
        statement: str,
        parameters: Sequence[Any] | Mapping[str, Any] | None,
    ) -> tuple[Any, Any]:
        if parameters is None or isinstance(parameters, Mapping):
            return text(statement), parameters or {}

        parameter_names = [f"p{index}" for index in range(statement.count("?"))]
        if len(parameter_names) != len(parameters):
            raise ValueError("SQL parameter count does not match the statement.")
        translated = statement
        for name in parameter_names:
            translated = translated.replace("?", f":{name}", 1)
        return text(translated), dict(zip(parameter_names, parameters))

    def execute(
        self,
        statement: str,
        parameters: Sequence[Any] | Mapping[str, Any] | None = None,
    ) -> _CoreResult:
        if statement.strip().upper() == "BEGIN IMMEDIATE":
            if self.dialect.name == "sqlite":
                result = self._connection.exec_driver_sql("BEGIN IMMEDIATE")
            else:
                result = self._connection.execute(
                    text("SELECT pg_advisory_xact_lock(:lock_id)"),
                    {"lock_id": _POSTGRES_ADMIN_LOCK_ID},
                )
                result.fetchone()
            return _CoreResult(result)

        if (
            self.dialect.name == "postgresql"
            and statement.lstrip().upper().startswith("INSERT")
        ):
            table_match = re.search(
                r"\bINTO\s+([A-Za-z_][A-Za-z0-9_]*)",
                statement,
                re.IGNORECASE,
            )
            primary_key = {
                "admins": "admin_id",
                "service_counters": "counter_id",
                "queue_tokens": "token_id",
                "queue_history": "history_id",
            }.get(table_match.group(1).lower()) if table_match else None
            if primary_key and " RETURNING " not in statement.upper():
                statement = statement.rstrip().rstrip(";") + f" RETURNING {primary_key}"

        sql, bound = self._bind_parameters(statement, parameters)
        return _CoreResult(self._connection.execute(sql, bound))

    def executemany(
        self,
        statement: str,
        parameters: Sequence[Sequence[Any]],
    ) -> _CoreResult:
        if not parameters:
            return _CoreResult(self._connection.execute(text("SELECT 1 WHERE 1 = 0")))
        sql, _ = self._bind_parameters(statement, parameters[0] if parameters else ())
        names = [f"p{index}" for index in range(statement.count("?"))]
        bound = [dict(zip(names, row)) for row in parameters]
        return _CoreResult(self._connection.execute(sql, bound))


def _normalized_database_url() -> URL | None:
    configured = os.environ.get("DATABASE_URL", "").strip()
    if not configured:
        return None

    lowered = configured.lower()
    if lowered.startswith("postgres://"):
        configured = "postgresql+psycopg://" + configured[len("postgres://") :]
    elif lowered.startswith("postgresql://"):
        configured = "postgresql+psycopg://" + configured[len("postgresql://") :]
    elif lowered.startswith("postgresql+psycopg2://"):
        configured = "postgresql+psycopg://" + configured[len("postgresql+psycopg2://") :]
    elif not lowered.startswith("postgresql+psycopg://"):
        raise DatabaseOperationError(
            "DATABASE_URL must use a supported PostgreSQL connection format."
        )

    try:
        return make_url(configured)
    except (ValueError, TypeError, SQLAlchemyError) as exc:
        raise DatabaseOperationError("DATABASE_URL is invalid.") from exc


def _get_engine() -> Engine:
    global _engine, _engine_key

    database_url = _normalized_database_url()
    if database_url is None:
        DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        url = URL.create("sqlite", database=str(DATABASE_PATH))
    else:
        url = database_url
    key = url.render_as_string(hide_password=False)

    with _engine_lock:
        if _engine is not None and _engine_key == key:
            return _engine
        if _engine is not None:
            _engine.dispose()

        if url.get_backend_name() == "sqlite":
            engine = create_engine(
                url,
                connect_args={"timeout": 30, "check_same_thread": False},
                poolclass=NullPool,
            )

            @event.listens_for(engine, "connect")
            def _enable_sqlite_foreign_keys(dbapi_connection: Any, _: Any) -> None:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys = ON")
                cursor.close()
        else:
            engine = create_engine(url, pool_pre_ping=True)

            @event.listens_for(engine, "connect")
            def _set_postgres_timezone(dbapi_connection: Any, _: Any) -> None:
                cursor = dbapi_connection.cursor()
                cursor.execute("SET TIME ZONE 'UTC'")
                cursor.close()

        _engine = engine
        _engine_key = key
        return engine


def _database_dialect() -> str:
    return _get_engine().dialect.name


def _inserted_id(
    connection: "_CoreConnection",
    result: _CoreResult,
    column: str,
) -> int:
    if connection.dialect.name == "sqlite":
        if result.lastrowid is None:
            raise DatabaseOperationError("Database did not return a generated identifier.")
        return int(result.lastrowid)
    row = result.fetchone()
    if row is None:
        raise DatabaseOperationError("Database did not return a generated identifier.")
    return int(row[column])


def check_database() -> None:
    """Verify connectivity without initializing or changing the database."""
    with _connection() as connection:
        connection.execute("SELECT 1")


def _hash_password(password: str) -> str:
    """Return a salted PBKDF2 hash suitable for storing instead of a password."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        PASSWORD_HASH_ALGORITHM,
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )
    return f"pbkdf2_{PASSWORD_HASH_ALGORITHM}${PASSWORD_HASH_ITERATIONS}${salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    """Compare a candidate password to a PBKDF2 hash without timing-sensitive equality."""
    try:
        scheme, iterations_text, salt_hex, digest_hex = stored_hash.split("$", maxsplit=3)
        if scheme != f"pbkdf2_{PASSWORD_HASH_ALGORITHM}":
            raise ValueError("unsupported password hash scheme")
        iterations = int(iterations_text)
        if iterations <= 0:
            raise ValueError("invalid password hash iteration count")
        salt = bytes.fromhex(salt_hex)
        expected_digest = bytes.fromhex(digest_hex)
    except ValueError as exc:
        raise DatabaseOperationError("Stored admin password hash is invalid.") from exc

    candidate_digest = hashlib.pbkdf2_hmac(
        PASSWORD_HASH_ALGORITHM,
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(candidate_digest, expected_digest)


def initialize_database() -> None:
    """Seed an admin after an explicit schema migration has been applied.

    Run ``python -m alembic upgrade head`` before the first application start.
    Set ``SMARTQUEUE_ADMIN_USERNAME`` and ``SMARTQUEUE_ADMIN_PASSWORD`` when
    the admins table is empty. Existing admin accounts are preserved.
    """
    with _connection() as connection:
        required_tables = set(_metadata.tables)
        existing_tables = set(inspect(connection._connection).get_table_names())
        missing_tables = sorted(
            (required_tables | {"alembic_version"}) - existing_tables
        )
        if missing_tables:
            raise RuntimeError(
                "The database schema is not initialized or revisioned. For a new "
                "database, run 'python -m alembic upgrade head'. For an existing "
                "database, verify its schema before running 'python -m alembic stamp head'."
            )

    # Seed only an empty admins table; never replace or reset an existing account.
    with _connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        admin_exists = connection.execute("SELECT 1 FROM admins LIMIT 1").fetchone()
        if admin_exists is None:
            username = os.environ.get("SMARTQUEUE_ADMIN_USERNAME", "").strip()
            password = os.environ.get("SMARTQUEUE_ADMIN_PASSWORD", "")
            if not username or not password:
                raise RuntimeError(
                    "No admin account exists. Set SMARTQUEUE_ADMIN_USERNAME and "
                    "SMARTQUEUE_ADMIN_PASSWORD before initializing the database."
                )
            seed_result = connection.execute(
                "INSERT INTO admins (username, password_hash) VALUES (?, ?)",
                (username, _hash_password(password)),
            )
            if connection.dialect.name == "postgresql":
                seed_result.fetchone()


def _new_tracking_reference(
    used_references: set[str] | None = None,
    connection: "_CoreConnection | None" = None,
) -> str:
    """Generate an unused cryptographically strong token tracking reference."""
    while True:
        reference = secrets.token_urlsafe(32)
        if used_references is not None and reference in used_references:
            continue
        if connection is not None and connection.execute(
            "SELECT 1 FROM queue_tokens WHERE tracking_reference = ?",
            (reference,),
        ).fetchone():
            continue
        if used_references is not None:
            used_references.add(reference)
        if connection is not None:
            return reference
        return reference


def _is_tracking_reference(reference: Any) -> bool:
    """Return whether a value has the format produced by token_urlsafe(32)."""
    return isinstance(reference, str) and re.fullmatch(
        r"[A-Za-z0-9_-]{43}",
        reference,
    ) is not None


def authenticate_admin(username: str, password: str) -> bool:
    """Return whether the supplied username and password match an admin account."""
    try:
        with _connection() as connection:
            row = connection.execute(
                "SELECT password_hash FROM admins WHERE username = ?",
                (username,),
            ).fetchone()
    except DatabaseOperationError:
        raise
    if row is None:
        return False
    return _verify_password(password, row["password_hash"])


def add_counter(
    counter_name: str,
    service_type: str,
    active_counters: int,
    avg_service_time: float,
) -> int:
    """Add a service counter and return its generated counter ID."""
    if not counter_name.strip():
        raise ValueError("counter_name must not be empty.")
    if service_type not in SERVICE_TYPES:
        raise ValueError(f"service_type must be one of: {', '.join(sorted(SERVICE_TYPES))}.")
    if not 1 <= active_counters <= 5:
        raise ValueError("active_counters must be between 1 and 5.")
    if not math.isfinite(avg_service_time) or avg_service_time <= 0:
        raise ValueError("avg_service_time must be a finite number greater than zero.")

    with _connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO service_counters
                (counter_name, service_type, active_counters, avg_service_time)
            VALUES (?, ?, ?, ?)
            """,
            (counter_name.strip(), service_type, active_counters, avg_service_time),
        )
        return _inserted_id(connection, cursor, "counter_id")


def get_all_counters() -> list[dict[str, Any]]:
    """Return all service counters ordered by ID."""
    with _connection() as connection:
        rows = connection.execute(
            "SELECT * FROM service_counters ORDER BY counter_id"
        ).fetchall()
    return [dict(row) for row in rows]


def get_counter_by_id(counter_id: int) -> dict[str, Any] | None:
    """Return a counter by ID, or None if it does not exist."""
    with _connection() as connection:
        row = connection.execute(
            "SELECT * FROM service_counters WHERE counter_id = ?",
            (counter_id,),
        ).fetchone()
    return dict(row) if row is not None else None


def update_counter(
    counter_id: int,
    people_waiting: int,
    active_counters: int,
    avg_service_time: float,
    is_active: bool | int,
) -> bool:
    """Update a counter's live queue settings; return False if it was not found."""
    if people_waiting < 0:
        raise ValueError("people_waiting must be non-negative.")
    if not 1 <= active_counters <= 5:
        raise ValueError("active_counters must be between 1 and 5.")
    if not math.isfinite(avg_service_time) or avg_service_time <= 0:
        raise ValueError("avg_service_time must be a finite number greater than zero.")
    if is_active not in (0, 1, False, True):
        raise ValueError("is_active must be a boolean or 0/1.")

    with _connection() as connection:
        cursor = connection.execute(
            """
            UPDATE service_counters
            SET people_waiting = ?, active_counters = ?, avg_service_time = ?, is_active = ?
            WHERE counter_id = ?
            """,
            (people_waiting, active_counters, avg_service_time, int(is_active), counter_id),
        )
        return cursor.rowcount > 0


def delete_counter(counter_id: int) -> bool:
    """Delete a counter if it has no dependent queue tokens."""
    with _connection() as connection:
        cursor = connection.execute(
            "DELETE FROM service_counters WHERE counter_id = ?",
            (counter_id,),
        )
        return cursor.rowcount > 0


def generate_token(counter_id: int, visitor_name: str | None = None) -> dict[str, Any]:
    """Create a unique daily, per-counter token with Waiting status.

    The write transaction is serialized and a unique index provides a second
    safeguard against duplicate token numbers.
    """
    today_prefix = f"{datetime.now(timezone.utc):%Y%m%d}-C{counter_id:03d}-"
    with _connection() as connection:
        if connection.dialect.name == "sqlite":
            connection.execute("BEGIN IMMEDIATE")
        counter = connection.execute(
            "SELECT is_active FROM service_counters WHERE counter_id = ?"
            + (" FOR UPDATE" if connection.dialect.name == "postgresql" else ""),
            (counter_id,),
        ).fetchone()
        if counter is None:
            raise ValueError(f"Service counter {counter_id} does not exist.")
        if not counter["is_active"]:
            raise ValueError(f"Service counter {counter_id} is inactive.")

        sequence_start = len(today_prefix) + 1
        if connection.dialect.name == "postgresql":
            latest_sequence = connection.execute(
                """
                SELECT COALESCE(MAX(
                    CASE
                        WHEN SUBSTR(token_number, ?) ~ '^[0-9]+$'
                        THEN CAST(SUBSTR(token_number, ?) AS BIGINT)
                        ELSE 0
                    END
                ), 0)
                FROM queue_tokens
                WHERE counter_id = ? AND token_number LIKE ?
                """,
                (sequence_start, sequence_start, counter_id, f"{today_prefix}%"),
            ).fetchone()[0]
        else:
            latest_sequence = connection.execute(
                """
                SELECT COALESCE(MAX(CAST(SUBSTR(token_number, ?) AS INTEGER)), 0)
                FROM queue_tokens
                WHERE counter_id = ? AND token_number LIKE ?
                """,
                (sequence_start, counter_id, f"{today_prefix}%"),
            ).fetchone()[0]
        token_number = f"{today_prefix}{int(latest_sequence) + 1:04d}"
        tracking_reference = _new_tracking_reference(connection=connection)
        cursor = connection.execute(
            """
            INSERT INTO queue_tokens
                (token_number, tracking_reference, counter_id, visitor_name, status)
            VALUES (?, ?, ?, ?, 'Waiting')
            """,
            (token_number, tracking_reference, counter_id, visitor_name),
        )
        token_id = _inserted_id(connection, cursor, "token_id")
        row = connection.execute(
            "SELECT * FROM queue_tokens WHERE token_id = ?",
            (token_id,),
        ).fetchone()
    return dict(row)


def get_token_by_tracking_reference(reference: str) -> dict[str, Any] | None:
    """Return a token only when its secure tracking reference matches exactly."""
    if not _is_tracking_reference(reference):
        return None
    with _connection() as connection:
        row = connection.execute(
            "SELECT * FROM queue_tokens WHERE tracking_reference = ?",
            (reference,),
        ).fetchone()
    return dict(row) if row is not None else None


def get_queue_position_by_tracking_reference(reference: str) -> int | None:
    """Return the number of waiting visitors ahead using only a secure reference."""
    if not _is_tracking_reference(reference):
        return None
    with _connection() as connection:
        token = connection.execute(
            """
            SELECT counter_id, created_at, status
            FROM queue_tokens
            WHERE tracking_reference = ?
            """,
            (reference,),
        ).fetchone()
        if token is None or token["status"] != "Waiting":
            return None

        ahead_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM queue_tokens
            WHERE counter_id = ?
              AND status = 'Waiting'
              AND (created_at < ? OR (created_at = ? AND token_id < (
                  SELECT token_id FROM queue_tokens WHERE tracking_reference = ?
              )))
            """,
            (
                token["counter_id"],
                token["created_at"],
                token["created_at"],
                reference,
            ),
        ).fetchone()[0]
    return int(ahead_count)


def get_waiting_tokens(counter_id: int) -> list[dict[str, Any]]:
    """Return a counter's waiting tokens in queue order."""
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM queue_tokens
            WHERE counter_id = ? AND status = 'Waiting'
            ORDER BY created_at, token_id
            """,
            (counter_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_active_queue_tokens(counter_id: int) -> list[dict[str, Any]]:
    """Return waiting and serving tokens for a counter in queue order."""
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM queue_tokens
            WHERE counter_id = ? AND status IN ('Waiting', 'Serving')
            ORDER BY created_at, token_id
            """,
            (counter_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_queue_tokens(
    status: str | None = None,
    service_type: str | None = None,
) -> list[dict[str, Any]]:
    """Return admin queue fields without exposing bearer tracking references."""
    if status is not None and status not in TOKEN_STATUSES:
        raise ValueError(f"status must be one of: {', '.join(sorted(TOKEN_STATUSES))}.")
    if service_type is not None and service_type not in SERVICE_TYPES:
        raise ValueError(
            f"service_type must be one of: {', '.join(sorted(SERVICE_TYPES))}."
        )

    conditions: list[str] = []
    parameters: list[str] = []
    if status is not None:
        conditions.append("queue_tokens.status = ?")
        parameters.append(status)
    if service_type is not None:
        conditions.append("service_counters.service_type = ?")
        parameters.append(service_type)
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with _connection() as connection:
        rows = connection.execute(
            f"""
            SELECT queue_tokens.token_id, queue_tokens.token_number,
                   service_counters.service_type, service_counters.counter_name,
                   queue_tokens.status, queue_tokens.created_at
            FROM queue_tokens
            INNER JOIN service_counters
                ON service_counters.counter_id = queue_tokens.counter_id
            {where_clause}
            ORDER BY queue_tokens.created_at, queue_tokens.token_id
            """,
            parameters,
        ).fetchall()
    return [dict(row) for row in rows]


def has_active_token_for_visitor(counter_id: int, visitor_name: str) -> bool:
    """Check for a same-name active token without returning another visitor's record."""
    if not visitor_name.strip():
        return False
    with _connection() as connection:
        row = connection.execute(
            """
            SELECT 1
            FROM queue_tokens
            WHERE counter_id = ?
              AND status IN ('Waiting', 'Serving')
              AND lower(trim(visitor_name)) = lower(trim(?))
            LIMIT 1
            """,
            (counter_id, visitor_name),
        ).fetchone()
    return row is not None


def get_token_by_id(token_id: int) -> dict[str, Any] | None:
    """Return a token by ID, or None if it does not exist."""
    with _connection() as connection:
        row = connection.execute(
            "SELECT * FROM queue_tokens WHERE token_id = ?",
            (token_id,),
        ).fetchone()
    return dict(row) if row is not None else None


def update_token_status(token_id: int, status: str) -> bool:
    """Set a token to Waiting, Serving, or Served; return False if not found."""
    if status not in TOKEN_STATUSES:
        raise ValueError(f"status must be one of: {', '.join(sorted(TOKEN_STATUSES))}.")
    with _connection() as connection:
        cursor = connection.execute(
            """
            UPDATE queue_tokens
            SET status = ?,
                served_at = CASE
                    WHEN ? = 'Served' THEN COALESCE(served_at, CURRENT_TIMESTAMP)
                    ELSE served_at
                END
            WHERE token_id = ?
            """,
            (status, status, token_id),
        )
        return cursor.rowcount > 0


def get_queue_position(token_id: int) -> int | None:
    """Return the number of waiting visitors ahead, or None if token isn't waiting."""
    with _connection() as connection:
        token = connection.execute(
            """
            SELECT counter_id, created_at, status
            FROM queue_tokens
            WHERE token_id = ?
            """,
            (token_id,),
        ).fetchone()
        if token is None or token["status"] != "Waiting":
            return None

        ahead_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM queue_tokens
            WHERE counter_id = ?
              AND status = 'Waiting'
              AND (created_at < ? OR (created_at = ? AND token_id < ?))
            """,
            (
                token["counter_id"],
                token["created_at"],
                token["created_at"],
                token_id,
            ),
        ).fetchone()[0]
    return int(ahead_count)


def get_queue_statistics() -> dict[str, Any]:
    """Return counter/token totals and waiting-token counts grouped by counter."""
    served_today_expression = (
        "CAST(queue_tokens.served_at AS DATE) = CURRENT_DATE"
        if _database_dialect() == "postgresql"
        else "date(queue_tokens.served_at) = date('now')"
    )
    with _connection() as connection:
        totals = connection.execute(
            f"""
            SELECT
                COUNT(DISTINCT service_counters.counter_id) AS total_counters,
                COUNT(DISTINCT CASE WHEN service_counters.is_active = 1
                                     THEN service_counters.counter_id END) AS active_counters,
                SUM(CASE WHEN queue_tokens.status = 'Waiting' THEN 1 ELSE 0 END) AS waiting_tokens,
                SUM(CASE WHEN queue_tokens.status = 'Serving' THEN 1 ELSE 0 END) AS serving_tokens,
                SUM(CASE WHEN queue_tokens.status = 'Served' THEN 1 ELSE 0 END) AS served_tokens,
                SUM(CASE WHEN queue_tokens.served_at IS NOT NULL THEN 1 ELSE 0 END)
                    AS historically_served_tokens,
                SUM(
                    CASE
                        WHEN queue_tokens.status = 'Served'
                         AND {served_today_expression}
                        THEN 1 ELSE 0
                    END
                ) AS served_tokens_today
            FROM service_counters
            LEFT JOIN queue_tokens USING (counter_id)
            """
        ).fetchone()
        per_counter = connection.execute(
            """
            SELECT
                counters.counter_id,
                counters.counter_name,
                counters.service_type,
                counters.is_active,
                COUNT(tokens.token_id) AS waiting_tokens
            FROM service_counters AS counters
            LEFT JOIN queue_tokens AS tokens
                ON tokens.counter_id = counters.counter_id AND tokens.status = 'Waiting'
            GROUP BY counters.counter_id, counters.counter_name,
                     counters.service_type, counters.is_active
            ORDER BY counters.counter_id
            """
        ).fetchall()

    return {
        "total_counters": totals["total_counters"] or 0,
        "active_counters": totals["active_counters"] or 0,
        "waiting_tokens": totals["waiting_tokens"] or 0,
        "serving_tokens": totals["serving_tokens"] or 0,
        "served_tokens": totals["served_tokens"] or 0,
        "historically_served_tokens": totals["historically_served_tokens"] or 0,
        "served_tokens_today": totals["served_tokens_today"] or 0,
        "counters": [dict(row) for row in per_counter],
    }


def get_daily_visitor_statistics() -> list[dict[str, Any]]:
    """Return historical served-token counts grouped by their served calendar date."""
    if _database_dialect() == "postgresql":
        date_expression = "CAST(served_at AS DATE)"
        selected_date = "TO_CHAR(CAST(served_at AS DATE), 'YYYY-MM-DD')"
    else:
        date_expression = "date(served_at)"
        selected_date = date_expression
    with _connection() as connection:
        rows = connection.execute(
            f"""
            SELECT {selected_date} AS served_date, COUNT(token_id) AS visitor_count
            FROM queue_tokens
            WHERE served_at IS NOT NULL
            GROUP BY {date_expression}
            ORDER BY {date_expression} ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_service_token_statistics() -> list[dict[str, Any]]:
    """Return token counts grouped by service type and supported current status."""
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT
                service_counters.service_type AS service_type,
                queue_tokens.status AS status,
                COUNT(queue_tokens.token_id) AS token_count
            FROM queue_tokens
            INNER JOIN service_counters
                ON service_counters.counter_id = queue_tokens.counter_id
            WHERE queue_tokens.status IN (?, ?, ?)
            GROUP BY service_counters.service_type, queue_tokens.status
            ORDER BY service_counters.service_type, queue_tokens.status
            """,
            ("Waiting", "Serving", "Served"),
        ).fetchall()
    return [dict(row) for row in rows]


def add_queue_history(
    counter_id: int | None,
    people_waiting: int,
    actual_waiting_time: float,
    predicted_waiting_time: float,
) -> int:
    """Store a queue observation and return its generated history ID."""
    if people_waiting < 0:
        raise ValueError("people_waiting must be non-negative.")
    if (
        not math.isfinite(actual_waiting_time)
        or not math.isfinite(predicted_waiting_time)
        or actual_waiting_time < 0
        or predicted_waiting_time < 0
    ):
        raise ValueError("Waiting times must be finite and non-negative.")
    with _connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO queue_history
                (counter_id, people_waiting, actual_waiting_time, predicted_waiting_time)
            VALUES (?, ?, ?, ?)
            """,
            (counter_id, people_waiting, actual_waiting_time, predicted_waiting_time),
        )
        return _inserted_id(connection, cursor, "history_id")


def get_queue_history() -> list[dict[str, Any]]:
    """Return all saved queue observations, newest first."""
    with _connection() as connection:
        rows = connection.execute(
            "SELECT * FROM queue_history ORDER BY recorded_at DESC, history_id DESC"
        ).fetchall()
    return [dict(row) for row in rows]