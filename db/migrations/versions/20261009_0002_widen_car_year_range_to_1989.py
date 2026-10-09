"""widen car year range to 1989

The inventory moved from fictional 1970s cars to real icons of the 1960s-1980s (ADR-0011),
including a 1987 Buick Grand National, which the old CHECK (1960-1979) rejects.

Written by hand: `alembic revision --autogenerate` does not detect changes inside CHECK
constraints. A CHECK cannot be altered in place, so it is dropped and recreated.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-09 10:40:12.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_cars_year_range"), "cars", type_="check")
    op.create_check_constraint(op.f("ck_cars_year_range"), "cars", "year BETWEEN 1960 AND 1989")


def downgrade() -> None:
    # Fails if a post-1979 car exists: delete those rows first. Downgrades must be honest.
    op.drop_constraint(op.f("ck_cars_year_range"), "cars", type_="check")
    op.create_check_constraint(op.f("ck_cars_year_range"), "cars", "year BETWEEN 1960 AND 1979")
