"""Create the existing SmartQueue schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admins",
        sa.Column("admin_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("admin_id"),
        sa.UniqueConstraint("username"),
        sqlite_autoincrement=True,
    )
    op.create_table(
        "service_counters",
        sa.Column("counter_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("counter_name", sa.Text(), nullable=False),
        sa.Column("service_type", sa.Text(), nullable=False),
        sa.Column("people_waiting", sa.Integer(), server_default=sa.text("0")),
        sa.Column("active_counters", sa.Integer(), server_default=sa.text("1")),
        sa.Column("avg_service_time", sa.Float(), server_default=sa.text("5")),
        sa.Column("is_active", sa.Integer(), server_default=sa.text("1")),
        sa.PrimaryKeyConstraint("counter_id"),
        sqlite_autoincrement=True,
    )
    op.create_table(
        "queue_tokens",
        sa.Column("token_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("token_number", sa.Text(), nullable=False),
        sa.Column("tracking_reference", sa.Text(), nullable=False),
        sa.Column("counter_id", sa.Integer(), nullable=False),
        sa.Column("visitor_name", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'Waiting'")),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("served_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["counter_id"], ["service_counters.counter_id"]),
        sa.PrimaryKeyConstraint("token_id"),
        sa.UniqueConstraint("tracking_reference"),
        sqlite_autoincrement=True,
    )
    op.create_index(
        "idx_queue_tokens_counter_number",
        "queue_tokens",
        ["counter_id", "token_number"],
        unique=True,
    )
    op.create_table(
        "queue_history",
        sa.Column("history_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("counter_id", sa.Integer(), nullable=True),
        sa.Column("people_waiting", sa.Integer(), nullable=True),
        sa.Column("actual_waiting_time", sa.Float(), nullable=True),
        sa.Column("predicted_waiting_time", sa.Float(), nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("history_id"),
        sqlite_autoincrement=True,
    )


def downgrade() -> None:
    raise RuntimeError(
        "SmartQueue's initial schema migration is intentionally irreversible."
    )
