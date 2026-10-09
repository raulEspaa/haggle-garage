"""create adk schema for agent sessions

ADK's DatabaseSessionService creates and migrates its own tables (sessions, events, states).
They live in a separate `adk` schema so that:
* our migrations and `alembic check` (which only look at `public`) never see them,
* the seller's DB role can later get full rights on `adk` and minimal rights on `public`.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-09 12:10:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS adk")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS adk CASCADE")
