"""Isolated Alembic migration checks using temporary SQLite databases."""

from __future__ import annotations

import os
import sys
import tempfile
from io import StringIO
from pathlib import Path
from typing import Callable

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database import db


REVISION = "0001_initial_schema"


def _config() -> Config:
    return Config(str(PROJECT_ROOT / "alembic.ini"))


def _run(name: str, test: Callable[[], None]) -> bool:
    try:
        test()
    except Exception as exc:
        print(f"FAIL: {name} - {type(exc).__name__}: {exc}")
        return False
    print(f"PASS: {name}")
    return True


def main() -> int:
    original_path = db.DATABASE_PATH
    environment_names = (
        "DATABASE_URL",
        "SMARTQUEUE_ADMIN_USERNAME",
        "SMARTQUEUE_ADMIN_PASSWORD",
    )
    original_environment = {name: os.environ.get(name) for name in environment_names}
    results: list[bool] = []

    try:
        with tempfile.TemporaryDirectory(prefix="smartqueue-migration-tests-") as root:
            os.environ.pop("DATABASE_URL", None)
            os.environ.pop("SMARTQUEUE_ADMIN_USERNAME", None)
            os.environ.pop("SMARTQUEUE_ADMIN_PASSWORD", None)
            config = _config()

            def use_database(name: str) -> Path:
                db.DATABASE_PATH = Path(root) / name
                return db.DATABASE_PATH

            def initialization_does_not_create_schema() -> None:
                use_database("unmigrated.sqlite")
                try:
                    db.initialize_database()
                except RuntimeError as exc:
                    assert "alembic upgrade head" in str(exc)
                else:
                    raise AssertionError("Initialization created the schema implicitly")
                assert inspect(db._get_engine()).get_table_names() == []

            results.append(
                _run(
                    "Require explicit migration before initialization",
                    initialization_does_not_create_schema,
                )
            )

            def migrate_empty_database() -> None:
                path = use_database("empty.sqlite")
                command.upgrade(config, "head")
                engine = db._get_engine()
                inspector = inspect(engine)
                expected_tables = {
                    "admins",
                    "service_counters",
                    "queue_tokens",
                    "queue_history",
                    "alembic_version",
                }
                assert expected_tables <= set(inspector.get_table_names())

                expected_columns = {
                    "admins": ["admin_id", "username", "password_hash"],
                    "service_counters": [
                        "counter_id",
                        "counter_name",
                        "service_type",
                        "people_waiting",
                        "active_counters",
                        "avg_service_time",
                        "is_active",
                    ],
                    "queue_tokens": [
                        "token_id",
                        "token_number",
                        "tracking_reference",
                        "counter_id",
                        "visitor_name",
                        "status",
                        "created_at",
                        "served_at",
                    ],
                    "queue_history": [
                        "history_id",
                        "counter_id",
                        "people_waiting",
                        "actual_waiting_time",
                        "predicted_waiting_time",
                        "recorded_at",
                    ],
                }
                for table_name, columns in expected_columns.items():
                    reflected_columns = inspector.get_columns(table_name)
                    assert [column["name"] for column in reflected_columns] == columns

                counter_columns = {
                    column["name"]: column
                    for column in inspector.get_columns("service_counters")
                }
                assert (
                    counter_columns["counter_name"]["type"].__class__.__name__
                    == "TEXT"
                )
                assert (
                    counter_columns["avg_service_time"]["type"].__class__.__name__
                    == "FLOAT"
                )
                assert counter_columns["people_waiting"]["default"] == "0"
                assert counter_columns["active_counters"]["default"] == "1"
                assert counter_columns["avg_service_time"]["default"] == "5"
                assert counter_columns["is_active"]["default"] == "1"

                token_columns = {
                    column["name"]: column
                    for column in inspector.get_columns("queue_tokens")
                }
                assert token_columns["tracking_reference"]["nullable"] is False
                assert token_columns["status"]["default"] == "'Waiting'"
                assert token_columns["created_at"]["default"] == "CURRENT_TIMESTAMP"
                assert token_columns["served_at"]["nullable"] is True
                history_columns = {
                    column["name"]: column
                    for column in inspector.get_columns("queue_history")
                }
                assert history_columns["recorded_at"]["default"] == "CURRENT_TIMESTAMP"

                assert {
                    tuple(constraint["column_names"])
                    for constraint in inspector.get_unique_constraints("admins")
                } == {("username",)}
                assert {
                    tuple(constraint["column_names"])
                    for constraint in inspector.get_unique_constraints("queue_tokens")
                } == {("tracking_reference",)}
                assert {
                    (index["name"], tuple(index["column_names"]), index["unique"])
                    for index in inspector.get_indexes("queue_tokens")
                } == {
                    (
                        "idx_queue_tokens_counter_number",
                        ("counter_id", "token_number"),
                        True,
                    )
                }
                assert inspector.get_foreign_keys("queue_tokens")[0][
                    "constrained_columns"
                ] == ["counter_id"]
                assert inspector.get_foreign_keys("queue_history") == []

                with engine.connect() as connection:
                    revision = connection.execute(
                        db.text("SELECT version_num FROM alembic_version")
                    ).scalar_one()
                    token_ddl = connection.execute(
                        db.text(
                            "SELECT sql FROM sqlite_master "
                            "WHERE type = 'table' AND name = 'queue_tokens'"
                        )
                    ).scalar_one()
                assert revision == REVISION
                assert "AUTOINCREMENT" in token_ddl
                assert path.is_file()
                command.check(config)

            results.append(
                _run(
                    "Upgrade empty SQLite database and verify schema",
                    migrate_empty_database,
                )
            )

            def upgrade_is_idempotent_and_preserves_rows() -> None:
                use_database("empty.sqlite")
                engine = db._get_engine()
                with engine.begin() as connection:
                    connection.execute(
                        db._service_counters.insert().values(
                            counter_id=42,
                            counter_name="Migration Test Counter",
                            service_type="Admission",
                        )
                    )
                    connection.execute(
                        db._queue_tokens.insert().values(
                            token_id=77,
                            token_number="MIGRATION-TEST",
                            tracking_reference="x" * 43,
                            counter_id=42,
                        )
                    )

                command.upgrade(_config(), "head")
                with engine.connect() as connection:
                    counter = connection.execute(
                        select(db._service_counters.c.counter_name).where(
                            db._service_counters.c.counter_id == 42
                        )
                    ).scalar_one()
                    token_number = connection.execute(
                        select(db._queue_tokens.c.token_number).where(
                            db._queue_tokens.c.token_id == 77
                        )
                    ).scalar_one()
                    revision = connection.execute(
                        db.text("SELECT version_num FROM alembic_version")
                    ).scalar_one()
                assert counter == "Migration Test Counter"
                assert token_number == "MIGRATION-TEST"
                assert revision == REVISION

            results.append(
                _run(
                    "Detect current revision and preserve data on repeat upgrade",
                    upgrade_is_idempotent_and_preserves_rows,
                )
            )

            def stamp_existing_schema_without_rewriting_data() -> None:
                use_database("existing.sqlite")
                engine = db._get_engine()
                db._metadata.create_all(engine)
                with engine.begin() as connection:
                    connection.execute(
                        db._service_counters.insert().values(
                            counter_id=91,
                            counter_name="Existing Local Counter",
                            service_type="Admission",
                        )
                    )
                command.stamp(_config(), "head")
                command.upgrade(_config(), "head")

                with engine.connect() as connection:
                    row = connection.execute(
                        select(
                            db._service_counters.c.counter_name,
                            db._service_counters.c.counter_id,
                        ).where(db._service_counters.c.counter_id == 91)
                    ).one()
                assert row == ("Existing Local Counter", 91)

            results.append(
                _run(
                    "Stamp an existing schema without changing its data",
                    stamp_existing_schema_without_rewriting_data,
                )
            )

            def compile_postgresql_migration_offline() -> None:
                os.environ["DATABASE_URL"] = "postgresql://localhost/smartqueue_migration_test"
                postgres_config = Config(
                    str(PROJECT_ROOT / "alembic.ini"),
                    output_buffer=StringIO(),
                )
                command.upgrade(postgres_config, "head", sql=True)
                sql = postgres_config.output_buffer.getvalue()
                assert "CREATE TABLE admins" in sql
                assert "CREATE TABLE queue_tokens" in sql
                assert "SERIAL" in sql
                assert (
                    "FOREIGN KEY(counter_id)" in sql
                    or "FOREIGN KEY (counter_id)" in sql
                )
                assert "CREATE UNIQUE INDEX idx_queue_tokens_counter_number" in sql

            results.append(
                _run(
                    "Compile PostgreSQL migration SQL without a connection",
                    compile_postgresql_migration_offline,
                )
            )
    finally:
        db.DATABASE_PATH = original_path
        for name, value in original_environment.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    passed = sum(results)
    failed = len(results) - passed
    print(f"\nMigration test summary: {passed} passed, {failed} failed.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
