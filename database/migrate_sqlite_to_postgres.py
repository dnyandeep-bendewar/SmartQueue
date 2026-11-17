
import os
import sqlite3
import sys
from pathlib import Path

from sqlalchemy import create_engine, text


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

SOURCE = Path("database/smartqueue_pre_supabase_backup.db")

TABLES = [
    "admins",
    "service_counters",
    "queue_tokens",
    "queue_history",
]

SEQUENCE_COLUMNS = {
    "admins": "admin_id",
    "service_counters": "counter_id",
    "queue_tokens": "token_id",
    "queue_history": "history_id",
}

EXPECTED_REVISION = "0001_initial_schema"


# --------------------------------------------------
# SOURCE DATABASE INSPECTION
# --------------------------------------------------

def read_sqlite_backup():
    """Read and validate the SQLite backup."""

    if not SOURCE.is_file():
        raise RuntimeError("SQLite backup file not found.")

    records = {}
    source_columns = {}

    with sqlite3.connect(SOURCE) as source:
        source.row_factory = sqlite3.Row

        integrity = source.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        if integrity != "ok":
            raise RuntimeError("SQLite backup integrity check failed.")

        for table in TABLES:

            source_columns[table] = [
                row["name"]
                for row in source.execute(
                    f"PRAGMA table_info({table})"
                ).fetchall()
            ]

            if not source_columns[table]:
                raise RuntimeError(
                    f"Source table missing or has no columns: {table}"
                )

            records[table] = [
                dict(row)
                for row in source.execute(
                    f'SELECT * FROM "{table}"'
                ).fetchall()
            ]

    return records, source_columns


# --------------------------------------------------
# DESTINATION VALIDATION
# --------------------------------------------------

def verify_destination(conn, source_columns):
    """Verify Supabase schema and ensure destination is empty."""

    revision = conn.execute(
        text("SELECT version_num FROM alembic_version")
    ).scalar_one()

    if revision != EXPECTED_REVISION:
        raise RuntimeError("Unexpected Alembic migration revision.")

    for table in TABLES:

        count = conn.execute(
            text(f'SELECT COUNT(*) FROM "{table}"')
        ).scalar_one()

        if count != 0:
            raise RuntimeError(
                f"Destination table {table} is not empty. "
                "Migration cancelled."
            )

        destination_columns = conn.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = :table
                ORDER BY ordinal_position
            """),
            {"table": table},
        ).scalars().all()

        if source_columns[table] != destination_columns:
            raise RuntimeError(
                f"Column mismatch detected in table {table}."
            )


# --------------------------------------------------
# DATA IMPORT
# --------------------------------------------------

def import_records(conn, records):
    """Import records in foreign-key-safe order."""

    for table in TABLES:

        rows = records[table]

        if not rows:
            print(f"{table}: 0 records (nothing to import)")
            continue

        columns = list(rows[0].keys())

        quoted_columns = ", ".join(
            f'"{column}"' for column in columns
        )

        parameters = ", ".join(
            f":{column}" for column in columns
        )

        statement = text(
            f'INSERT INTO "{table}" '
            f'({quoted_columns}) VALUES ({parameters})'
        )

        conn.execute(statement, rows)

        print(f"{table}: imported {len(rows)} records")


# --------------------------------------------------
# POSTGRESQL SEQUENCE SYNCHRONIZATION
# --------------------------------------------------

def synchronize_sequences(conn):
    """Advance PostgreSQL sequences after explicit ID imports."""

    for table, column in SEQUENCE_COLUMNS.items():

        max_id = conn.execute(
            text(f'SELECT MAX("{column}") FROM "{table}"')
        ).scalar_one()

        # Empty tables retain their existing sequence state.
        if max_id is None:
            continue

        conn.execute(
            text("""
                SELECT setval(
                    pg_get_serial_sequence(
                        :table_name,
                        :column_name
                    ),
                    :max_id,
                    true
                )
            """),
            {
                "table_name": f"public.{table}",
                "column_name": column,
                "max_id": max_id,
            },
        )


# --------------------------------------------------
# POST-MIGRATION VALIDATION
# --------------------------------------------------

def verify_import(conn, records):
    """Verify imported counts and token relationships."""

    print("\nVerifying imported records:")

    for table in TABLES:

        expected = len(records[table])

        actual = conn.execute(
            text(f'SELECT COUNT(*) FROM "{table}"')
        ).scalar_one()

        print(f"{table}: expected={expected}, actual={actual}")

        if actual != expected:
            raise RuntimeError(
                f"Record count mismatch in {table}."
            )

    orphan_count = conn.execute(
        text("""
            SELECT COUNT(*)
            FROM queue_tokens q
            LEFT JOIN service_counters c
                ON q.counter_id = c.counter_id
            WHERE c.counter_id IS NULL
        """)
    ).scalar_one()

    if orphan_count != 0:
        raise RuntimeError(
            "Foreign-key verification failed: orphaned tokens found."
        )

    print("Token-to-counter relationships verified.")


# --------------------------------------------------
# MAIN MIGRATION
# --------------------------------------------------

def migrate():

    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured.")

    print("Reading SQLite backup...")

    records, source_columns = read_sqlite_backup()

    print("SQLite backup integrity verified.")

    for table in TABLES:
        print(f"{table}: {len(records[table])} source records")

    engine = create_engine(
        database_url,
        pool_pre_ping=True,
    )

    try:
        print("\nConnecting to Supabase PostgreSQL...")

        # One transaction for all data inserts and validation.
        with engine.begin() as conn:

            print("Connected successfully.")

            print("\nChecking destination schema and revision...")

            verify_destination(conn, source_columns)

            print("Destination verified and empty.")

            print("\nImporting records...")

            import_records(conn, records)

            print("\nSynchronizing PostgreSQL sequences...")

            synchronize_sequences(conn)

            print("\nValidating imported data...")

            verify_import(conn, records)

        print("\n" + "=" * 45)
        print("MIGRATION COMMITTED SUCCESSFULLY")
        print("=" * 45)

    finally:
        engine.dispose()


# --------------------------------------------------
# ENTRY POINT
# --------------------------------------------------

if __name__ == "__main__":

    try:
        migrate()

    except Exception as exc:

        print("\nMIGRATION FAILED")
        print("Error type:", type(exc).__name__)
        print(
            "The database transaction was rolled back "
            "if it had begun."
        )
        print("Inspect the database before attempting a retry.")

        sys.exit(1)
