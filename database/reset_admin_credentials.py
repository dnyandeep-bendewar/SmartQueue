"""Explicitly reset the existing administrator using environment credentials.

PowerShell (from the project root):
    # Stop FastAPI with Ctrl+C in its terminal before changing credentials.
    $env:SMARTQUEUE_ADMIN_USERNAME = "your-admin-username"
    # Set this only if more than one admin exists:
    # $env:SMARTQUEUE_ADMIN_RESET_CURRENT_USERNAME = "existing-admin-username"
    .\\.venv\\Scripts\\python.exe -m database.reset_admin_credentials
    # If SMARTQUEUE_ADMIN_PASSWORD is not set, the utility prompts securely.
    Remove-Item Env:\\SMARTQUEUE_ADMIN_RESET_CURRENT_USERNAME -ErrorAction SilentlyContinue
    Remove-Item Env:\\SMARTQUEUE_ADMIN_USERNAME -ErrorAction SilentlyContinue
    Remove-Item Env:\\SMARTQUEUE_ADMIN_PASSWORD -ErrorAction SilentlyContinue
    # Restart FastAPI after the reset to clear process-local sessions.
    .\\.venv\\Scripts\\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

If the database contains multiple admins, also set
SMARTQUEUE_ADMIN_RESET_CURRENT_USERNAME to the account that should be replaced.
This utility never initializes the schema or creates an administrator.
"""

from __future__ import annotations

import os
from getpass import getpass

from database import db


def reset_admin_credentials(
    username: str,
    password: str,
    *,
    current_username: str | None = None,
) -> None:
    """Replace one existing admin's credentials and verify the resulting login."""
    username = username.strip()
    if not username or len(username) > 150:
        raise ValueError("Admin username must contain between 1 and 150 characters.")
    if not password or len(password) > 1024:
        raise ValueError("Admin password must contain between 1 and 1024 characters.")
    if current_username is not None:
        current_username = current_username.strip()
        if not current_username:
            raise ValueError("Current admin username must not be blank.")

    password_hash = db._hash_password(password)

    with db._connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        admins = connection.execute(
            "SELECT admin_id, username FROM admins ORDER BY admin_id"
        ).fetchall()
        if not admins:
            raise RuntimeError(
                "No administrator exists. Initialize the database before resetting credentials."
            )

        if current_username is None:
            if len(admins) != 1:
                raise RuntimeError(
                    "Multiple administrators exist. Set "
                    "SMARTQUEUE_ADMIN_RESET_CURRENT_USERNAME to select one."
                )
            target = admins[0]
        else:
            target = next(
                (admin for admin in admins if admin["username"] == current_username),
                None,
            )
            if target is None:
                raise RuntimeError("The selected existing administrator was not found.")

        duplicate = connection.execute(
            "SELECT 1 FROM admins WHERE username = ? AND admin_id != ?",
            (username, target["admin_id"]),
        ).fetchone()
        if duplicate is not None:
            raise RuntimeError(
                "The requested username belongs to a different administrator."
            )

        connection.execute(
            "UPDATE admins SET username = ?, password_hash = ? WHERE admin_id = ?",
            (username, password_hash, target["admin_id"]),
        )

    if not db.authenticate_admin(username, password):
        raise RuntimeError(
            "Credential reset completed, but verification failed. "
            "Check the configured database."
        )


def main() -> int:
    username = os.environ.get("SMARTQUEUE_ADMIN_USERNAME", "")
    password = os.environ.get("SMARTQUEUE_ADMIN_PASSWORD", "")
    current_username = os.environ.get("SMARTQUEUE_ADMIN_RESET_CURRENT_USERNAME")

    try:
        if not password:
            password = getpass("New administrator password: ")
        reset_admin_credentials(
            username,
            password,
            current_username=current_username,
        )
    except ValueError as exc:
        print(f"Credential reset not performed: {exc}")
        return 1
    except RuntimeError as exc:
        print(f"Credential reset not performed: {exc}")
        return 1
    except (db.DatabaseOperationError, OSError):
        print(
            "Credential reset failed because the database could not be accessed. "
            "Confirm that it is initialized and that the application is stopped."
        )
        return 1

    print("Administrator credentials were reset and verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
