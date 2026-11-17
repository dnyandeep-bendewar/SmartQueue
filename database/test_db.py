"""Isolated integration checks for the SmartQueue database helpers.

Run from the project root with ``python database/test_db.py``. All writes are
made to a temporary database, not the application's ``smartqueue.db`` file.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from alembic import command
from alembic.config import Config

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database import db


def run_test(name: str, test: Callable[[], object]) -> bool:
    """Run one check and print a clear PASS or FAIL result."""
    try:
        test()
    except Exception as exc:
        print(f"FAIL: {name} — {type(exc).__name__}: {exc}")
        return False
    print(f"PASS: {name}")
    return True


def main() -> int:
    results: list[bool] = []
    state: dict[str, Any] = {}
    original_database_path = db.DATABASE_PATH
    environment_names = (
        "DATABASE_URL",
        "SMARTQUEUE_ADMIN_USERNAME",
        "SMARTQUEUE_ADMIN_PASSWORD",
        "SMARTQUEUE_ADMIN_RESET_CURRENT_USERNAME",
    )
    original_environment = {name: os.environ.get(name) for name in environment_names}

    try:
        with tempfile.TemporaryDirectory(prefix="smartqueue-db-tests-") as temp_dir:
            db.DATABASE_PATH = Path(temp_dir) / "smartqueue-test.db"
            os.environ.pop("DATABASE_URL", None)
            os.environ["SMARTQUEUE_ADMIN_USERNAME"] = "smartqueue-test-admin"
            os.environ["SMARTQUEUE_ADMIN_PASSWORD"] = "temporary-test-password"

            def apply_schema_migration() -> None:
                config = Config(str(PROJECT_ROOT / "alembic.ini"))
                command.upgrade(config, "head")

            results.append(
                run_test("Apply Alembic schema migration", apply_schema_migration)
            )

            def sqlite_foreign_keys_enabled() -> None:
                with db._connection() as connection:
                    enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0]
                    assert enabled == 1, "SQLite foreign-key enforcement is disabled"

            results.append(
                run_test("Initialize temporary database", db.initialize_database)
            )

            results.append(
                run_test("Check database connectivity", db.check_database)
            )
            results.append(
                run_test("Enable SQLite foreign keys", sqlite_foreign_keys_enabled)
            )

            def normalize_postgres_urls() -> None:
                os.environ["DATABASE_URL"] = "postgres://localhost/smartqueue_test"
                assert db._normalized_database_url().drivername == "postgresql+psycopg"
                os.environ["DATABASE_URL"] = (
                    "postgresql://localhost/smartqueue_test?sslmode=require"
                )
                url = db._normalized_database_url()
                assert url.drivername == "postgresql+psycopg"
                assert url.query["sslmode"] == "require"
                os.environ.pop("DATABASE_URL", None)

            results.append(
                run_test("Normalize supported PostgreSQL URLs", normalize_postgres_urls)
            )

            def select_postgres_without_connecting() -> None:
                os.environ["DATABASE_URL"] = "postgresql://localhost/smartqueue_test"
                assert db._get_engine().dialect.name == "postgresql"
                os.environ.pop("DATABASE_URL", None)
                assert db._get_engine().dialect.name == "sqlite"

            results.append(
                run_test("Select PostgreSQL from DATABASE_URL", select_postgres_without_connecting)
            )

            def authenticate_seeded_admin() -> None:
                authenticated = db.authenticate_admin(
                    "smartqueue-test-admin",
                    "temporary-test-password",
                )
                assert authenticated, "Admin authentication failed"

            results.append(
                run_test("Authenticate seeded admin", authenticate_seeded_admin)
            )

            def add_two_counters() -> None:
                state["counter_ids"] = [
                    db.add_counter("Admissions Desk", "Admission", 2, 6.0),
                    db.add_counter("Payments Desk", "Fee Payment", 1, 4.0),
                ]

            results.append(run_test("Add two service counters", add_two_counters))

            def retrieve_counters() -> None:
                counters = db.get_all_counters()
                assert len(counters) == 2, f"Expected 2 counters, got {len(counters)}"
                assert {counter["counter_id"] for counter in counters} == set(
                    state["counter_ids"]
                )
                state["counters"] = counters

            results.append(run_test("Retrieve all counters", retrieve_counters))

            def update_first_counter() -> None:
                counter_ids = state["counter_ids"]
                counter_id = counter_ids[0]
                assert db.update_counter(counter_id, 3, 3, 7.5, True)
                updated = db.get_counter_by_id(counter_id)
                assert updated is not None
                assert updated["people_waiting"] == 3
                assert updated["active_counters"] == 3
                assert updated["avg_service_time"] == 7.5

            results.append(run_test("Update a service counter", update_first_counter))

            def generate_three_tokens() -> None:
                counter_ids = state["counter_ids"]
                counter_id = counter_ids[0]
                tokens = [
                    db.generate_token(counter_id, "Visitor One"),
                    db.generate_token(counter_id, "Visitor Two"),
                    db.generate_token(counter_id, "Visitor Three"),
                ]
                assert len({token["token_number"] for token in tokens}) == 3
                assert len({token["tracking_reference"] for token in tokens}) == 3
                assert all(len(token["tracking_reference"]) == 43 for token in tokens)
                assert all(token["status"] == "Waiting" for token in tokens)
                state["tokens"] = tokens

            results.append(run_test("Generate three visitor tokens", generate_three_tokens))

            def track_token_by_opaque_reference() -> None:
                token = state["tokens"][0]
                found = db.get_token_by_tracking_reference(token["tracking_reference"])
                assert found is not None
                assert found["token_id"] == token["token_id"]
                assert db.get_queue_position_by_tracking_reference(
                    token["tracking_reference"]
                ) == 0
                assert db.get_token_by_tracking_reference("invalid-reference") is None

            results.append(
                run_test("Track token by secure reference", track_token_by_opaque_reference)
            )

            def concurrent_token_numbers_are_unique() -> None:
                counter_id = state["counter_ids"][1]
                with ThreadPoolExecutor(max_workers=8) as executor:
                    tokens = list(
                        executor.map(
                            lambda index: db.generate_token(
                                counter_id,
                                f"Concurrent Visitor {index}",
                            ),
                            range(12),
                        )
                    )
                numbers = [token["token_number"] for token in tokens]
                assert len(set(numbers)) == len(numbers)

            results.append(
                run_test("Serialize concurrent token generation", concurrent_token_numbers_are_unique)
            )

            def retrieve_waiting_tokens() -> None:
                counter_ids = state["counter_ids"]
                counter_id = counter_ids[0]
                tokens = db.get_waiting_tokens(counter_id)
                assert len(tokens) == 3, f"Expected 3 waiting tokens, got {len(tokens)}"
                assert all(token["status"] == "Waiting" for token in tokens)
                state["waiting_tokens"] = tokens

            results.append(run_test("Retrieve waiting tokens", retrieve_waiting_tokens))

            def check_queue_positions() -> None:
                tokens = state["waiting_tokens"]
                token_ids = [token["token_id"] for token in tokens]
                positions = [db.get_queue_position(token_id) for token_id in token_ids]
                assert positions == [0, 1, 2], f"Expected positions [0, 1, 2], got {positions}"

            results.append(run_test("Check queue positions", check_queue_positions))

            def update_token_statuses() -> None:
                tokens = state["tokens"]
                serving_id = tokens[0]["token_id"]
                served_id = tokens[1]["token_id"]
                assert db.update_token_status(serving_id, "Serving")
                assert db.update_token_status(served_id, "Served")
                serving_token = db.get_token_by_id(serving_id)
                served_token = db.get_token_by_id(served_id)
                assert serving_token is not None and serving_token["status"] == "Serving"
                assert served_token is not None and served_token["status"] == "Served"

            results.append(run_test("Mark tokens Serving and Served", update_token_statuses))

            def group_served_tokens_by_utc_date() -> None:
                trends = db.get_daily_visitor_statistics()
                assert trends
                assert trends[0]["served_date"]
                assert trends[0]["visitor_count"] == 1

            results.append(
                run_test("Group served tokens by date", group_served_tokens_by_utc_date)
            )

            def reset_admin_through_existing_utility() -> None:
                from database.reset_admin_credentials import reset_admin_credentials

                reset_admin_credentials(
                    "updated-test-admin",
                    "updated-temporary-test-password",
                    current_username="smartqueue-test-admin",
                )
                assert db.authenticate_admin(
                    "updated-test-admin",
                    "updated-temporary-test-password",
                )
                assert not db.authenticate_admin(
                    "smartqueue-test-admin",
                    "temporary-test-password",
                )

            results.append(
                run_test("Reset admin using database abstraction", reset_admin_through_existing_utility)
            )

            def add_history_record() -> None:
                counter_ids = state["counter_ids"]
                history_id = db.add_queue_history(counter_ids[0], 3, 18.5, 20.0)
                state["history_id"] = history_id

            results.append(run_test("Add a queue history record", add_history_record))

            def retrieve_statistics() -> None:
                statistics = db.get_queue_statistics()
                assert statistics["total_counters"] == 2
                assert statistics["active_counters"] == 2
                assert statistics["waiting_tokens"] == 13
                assert statistics["serving_tokens"] == 1
                assert statistics["served_tokens"] == 1

            results.append(run_test("Retrieve queue statistics", retrieve_statistics))

            def retrieve_history() -> None:
                history = db.get_queue_history()
                history_id = state["history_id"]
                matching_rows = [
                    row for row in history if row["history_id"] == history_id
                ]
                assert matching_rows, "Added history record was not returned"
                assert matching_rows[0]["people_waiting"] == 3
                assert matching_rows[0]["actual_waiting_time"] == 18.5
                assert matching_rows[0]["predicted_waiting_time"] == 20.0

            results.append(run_test("Retrieve queue history", retrieve_history))

            def reject_implicit_legacy_schema_change() -> None:
                legacy_path = Path(temp_dir) / "legacy.sqlite"
                legacy = sqlite3.connect(legacy_path)
                try:
                    legacy.executescript(
                        """
                        CREATE TABLE admins (
                            admin_id INTEGER PRIMARY KEY AUTOINCREMENT,
                            username TEXT UNIQUE NOT NULL,
                            password_hash TEXT NOT NULL
                        );
                        CREATE TABLE service_counters (
                            counter_id INTEGER PRIMARY KEY AUTOINCREMENT,
                            counter_name TEXT NOT NULL,
                            service_type TEXT NOT NULL,
                            people_waiting INTEGER DEFAULT 0,
                            active_counters INTEGER DEFAULT 1,
                            avg_service_time REAL DEFAULT 5,
                            is_active INTEGER DEFAULT 1
                        );
                        CREATE TABLE queue_tokens (
                            token_id INTEGER PRIMARY KEY AUTOINCREMENT,
                            token_number TEXT NOT NULL,
                            counter_id INTEGER NOT NULL,
                            visitor_name TEXT,
                            status TEXT DEFAULT 'Waiting',
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY (counter_id)
                                REFERENCES service_counters(counter_id)
                        );
                        INSERT INTO service_counters (counter_id, counter_name, service_type)
                        VALUES (7, 'Legacy Desk', 'Admission');
                        INSERT INTO queue_tokens
                            (token_id, token_number, counter_id, visitor_name)
                        VALUES (11, 'LEGACY-001', 7, 'Legacy Visitor');
                        """
                    )
                    legacy.commit()
                finally:
                    legacy.close()

                current_path = db.DATABASE_PATH
                db.DATABASE_PATH = legacy_path
                try:
                    try:
                        db.initialize_database()
                    except RuntimeError as exc:
                        assert (
                            "alembic upgrade head" in str(exc)
                            and "alembic stamp head" in str(exc)
                        )
                    else:
                        raise AssertionError("Unrevisioned schema was accepted")

                    legacy = sqlite3.connect(legacy_path)
                    try:
                        token = legacy.execute(
                            "SELECT token_id, token_number FROM queue_tokens"
                        ).fetchone()
                        columns = {
                            row[1]
                            for row in legacy.execute(
                                "PRAGMA table_info(queue_tokens)"
                            ).fetchall()
                        }
                    finally:
                        legacy.close()
                    assert token == (11, "LEGACY-001")
                    assert "tracking_reference" not in columns
                finally:
                    db.DATABASE_PATH = current_path

            results.append(
                run_test(
                    "Reject implicit changes to unrevisioned SQLite data",
                    reject_implicit_legacy_schema_change,
                )
            )
    finally:
        db.DATABASE_PATH = original_database_path
        for name, value in original_environment.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    passed = sum(results)
    failed = len(results) - passed
    print(f"\nTest summary: {passed} passed, {failed} failed.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
