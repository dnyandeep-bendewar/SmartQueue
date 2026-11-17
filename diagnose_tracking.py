"""Diagnose visitor token lookup against the configured SmartQueue database."""

from __future__ import annotations

from database import db


def main() -> None:
    """Look up a supplied tracking reference without changing database records."""
    try:
        db.initialize_database()
    except (db.DatabaseOperationError, RuntimeError) as exc:
        print(f"DATABASE EXCEPTION: Could not initialize the database: {exc}")
        return

    print(f"Database path: {db.DATABASE_PATH.resolve()}")
    reference = input("Enter the token tracking reference: ").strip()
    if not reference:
        print("TOKEN NOT FOUND: No tracking reference was entered.")
        return

    try:
        token = db.get_token_by_tracking_reference(reference)
        if token is None:
            print("TOKEN NOT FOUND: No token matches the supplied reference.")
            return

        counter_id = int(token["counter_id"])
        counter = db.get_counter_by_id(counter_id)
        service_type = (
            counter["service_type"] if counter is not None else "Unavailable"
        )

        print("TOKEN FOUND")
        print(f"Token number: {token['token_number']}")
        print(f"Service type: {service_type}")
        print(f"Current status: {token['status']}")
        print(f"Counter ID: {counter_id}")

        if token["status"] == "Waiting":
            queue_position = db.get_queue_position_by_tracking_reference(reference)
            if queue_position is None:
                print("Queue position: Unavailable")
            else:
                print(f"Queue position: {queue_position} people ahead")
    except (db.DatabaseOperationError, KeyError, TypeError, ValueError) as exc:
        print(f"DATABASE EXCEPTION: Could not complete token lookup: {exc}")


if __name__ == "__main__":
    main()
