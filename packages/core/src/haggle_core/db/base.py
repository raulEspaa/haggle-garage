"""Declarative base shared by all ORM models.

Two conventions are set here once, so that individual models stay short:

* `naming_convention`: deterministic constraint and index names. Alembic needs them to
  generate stable migrations, for example to drop a constraint by name later.
* `type_annotation_map`: `Mapped[str]` becomes Postgres TEXT (not VARCHAR), and `Mapped[datetime]`
  becomes TIMESTAMPTZ. In Postgres, TEXT is as fast as VARCHAR and never needs a length migration.
"""

from datetime import datetime

from sqlalchemy import DateTime, MetaData, Text
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {  # noqa: RUF012 (SQLAlchemy reads this class attribute)
        str: Text(),
        datetime: DateTime(timezone=True),
    }
