"""ORM models. The source of truth for the schema is this file plus the Alembic migrations.

Design notes (see docs/03-contracts.md §4):
* Money is stored as integer whole USD. Ratios use NUMERIC, never float.
* Enumerations are TEXT + CHECK constraints generated from the Python enums. Native Postgres
  ENUM types are harder to migrate: adding a value needs special DDL.
* Columns marked SECRET must never appear in API responses, logs or LLM prompts (except the
  floor at levels 1-2, which is the vulnerability under study).
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    Numeric,
    SmallInteger,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from haggle_core.db.base import Base
from haggle_core.domain import (
    CloseOutcome,
    Decision,
    EventKind,
    GameMode,
    GameStatus,
    LlmComponent,
    McpBackend,
    TurnRole,
)

EMBEDDING_DIMS = 768  # gemini-embedding-2 truncated to 768 dims (ADR-0005, docs/10-sources.md)


def one_of(column: str, values: type[Enum]) -> str:
    """Build a CHECK expression like `status IN ('open', 'deal')` from a Python enum."""
    allowed = ", ".join(f"'{member.value}'" for member in values)
    return f"{column} IN ({allowed})"


def _bigint_pk() -> Mapped[int]:
    return mapped_column(BigInteger, Identity(always=True), primary_key=True)


def _created_at() -> Mapped[datetime]:
    return mapped_column(server_default=func.now())


# --------------------------------------------------------------------------- catalog


class ModelSheet(Base):
    """A hand-written fact sheet about a (fictional) car model. Source for RAG."""

    __tablename__ = "model_sheets"

    id: Mapped[int] = _bigint_pk()
    slug: Mapped[str] = mapped_column(unique=True)
    make: Mapped[str]
    model: Mapped[str]
    years: Mapped[str]
    title: Mapped[str]
    body_md: Mapped[str]
    version: Mapped[int] = mapped_column(server_default=text("1"))
    updated_at: Mapped[datetime] = _created_at()


class SheetChunk(Base):
    """One retrievable section of a model sheet, with its embedding."""

    __tablename__ = "sheet_chunks"
    __table_args__ = (
        UniqueConstraint("sheet_id", "chunk_index"),
        # HNSW = approximate nearest-neighbour index. Overkill for ~30 rows, kept for learning.
        Index(
            "ix_sheet_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = _bigint_pk()
    sheet_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("model_sheets.id", ondelete="CASCADE")
    )
    chunk_index: Mapped[int] = mapped_column(SmallInteger)
    section: Mapped[str]
    content: Mapped[str]
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMS))
    token_count: Mapped[int]


class Car(Base):
    """A public listing. Everything here may be shown to players."""

    __tablename__ = "cars"
    __table_args__ = (
        CheckConstraint("year BETWEEN 1960 AND 1979", name="year_range"),
        CheckConstraint("mileage_mi >= 0", name="mileage_non_negative"),
        CheckConstraint("condition_grade BETWEEN 1 AND 5", name="condition_grade_range"),
        CheckConstraint("list_price_usd > 0", name="list_price_positive"),
    )

    id: Mapped[str] = mapped_column(primary_key=True)  # slug, e.g. "vantor-kestrel-rs-1970"
    make: Mapped[str]
    model: Mapped[str]
    year: Mapped[int] = mapped_column(SmallInteger)
    trim: Mapped[str | None]
    engine: Mapped[str]
    transmission: Mapped[str]
    mileage_mi: Mapped[int]
    exterior_color: Mapped[str]
    condition_grade: Mapped[int] = mapped_column(SmallInteger)  # 1 = concours ... 5 = project car
    list_price_usd: Mapped[int]
    description_md: Mapped[str]
    model_sheet_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("model_sheets.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = _created_at()


class PricingPolicy(Base):
    """Per-car negotiation policy. SECRET: it reveals the floor range."""

    __tablename__ = "pricing_policies"
    __table_args__ = (
        CheckConstraint("floor_min_usd > 0", name="floor_min_positive"),
        CheckConstraint("floor_max_usd >= floor_min_usd", name="floor_range_valid"),
        CheckConstraint("beta > 0 AND beta <= 3", name="beta_range"),
        CheckConstraint(
            "margin_min >= 0 AND margin_max >= margin_min AND margin_max < 1",
            name="margin_range",
        ),
        CheckConstraint("lowball_ratio > 0 AND lowball_ratio < 1", name="lowball_ratio_range"),
        CheckConstraint("price_step_usd > 0", name="price_step_positive"),
    )

    car_id: Mapped[str] = mapped_column(ForeignKey("cars.id", ondelete="CASCADE"), primary_key=True)
    floor_min_usd: Mapped[int]
    floor_max_usd: Mapped[int]
    beta: Mapped[Decimal] = mapped_column(Numeric(4, 2), server_default=text("0.50"))
    margin_min: Mapped[Decimal] = mapped_column(Numeric(4, 3), server_default=text("0.020"))
    margin_max: Mapped[Decimal] = mapped_column(Numeric(4, 3), server_default=text("0.060"))
    lowball_ratio: Mapped[Decimal] = mapped_column(Numeric(4, 3), server_default=text("0.550"))
    price_step_usd: Mapped[int] = mapped_column(server_default=text("100"))


# --------------------------------------------------------------------------- games


class Game(Base):
    """One negotiation. `id` doubles as the A2A contextId and the Langfuse session id."""

    __tablename__ = "games"
    __table_args__ = (
        CheckConstraint("level BETWEEN 1 AND 3", name="level_range"),
        CheckConstraint(one_of("mode", GameMode), name="mode_valid"),
        CheckConstraint(one_of("status", GameStatus), name="status_valid"),
        CheckConstraint("floor_usd > 0 AND floor_usd < list_price_usd", name="floor_below_list"),
        CheckConstraint("counter_margin >= 0 AND counter_margin < 1", name="counter_margin_range"),
        CheckConstraint("turn_cap > 0", name="turn_cap_positive"),
        CheckConstraint("turn_count >= 0 AND turn_count <= turn_cap", name="turn_count_range"),
        CheckConstraint(
            f"mcp_backend IS NULL OR {one_of('mcp_backend', McpBackend)}",
            name="mcp_backend_valid",
        ),
        Index("ix_games_client_ip_hash_created_at", "client_ip_hash", "created_at"),
        Index("ix_games_status_last_activity_at", "status", "last_activity_at"),
        Index("ix_games_eval_run_id", "eval_run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    car_id: Mapped[str] = mapped_column(ForeignKey("cars.id"))
    level: Mapped[int] = mapped_column(SmallInteger)
    mode: Mapped[str]
    buyer_persona: Mapped[str | None]
    list_price_usd: Mapped[int]  # snapshot at creation; the listing may change later
    floor_usd: Mapped[int]  # SECRET: sampled per game, non-round
    counter_margin: Mapped[Decimal] = mapped_column(Numeric(4, 3))  # SECRET
    turn_cap: Mapped[int] = mapped_column(SmallInteger, server_default=text("12"))
    turn_count: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    status: Mapped[str] = mapped_column(server_default=text(f"'{GameStatus.OPEN.value}'"))
    final_price_usd: Mapped[int | None]
    floor_guess_usd: Mapped[int | None]
    floor_guess_correct: Mapped[bool | None]
    mcp_backend: Mapped[str | None]
    model_id: Mapped[str | None]
    prompt_version: Mapped[str | None]
    client_ip_hash: Mapped[str | None]  # salted hash, never the raw IP
    game_token_hash: Mapped[str | None]
    eval_run_id: Mapped[str | None]
    created_at: Mapped[datetime] = _created_at()
    last_activity_at: Mapped[datetime] = _created_at()
    ended_at: Mapped[datetime | None]


class Turn(Base):
    """One transcript message. Written by the seller, which sees both sides in every mode."""

    __tablename__ = "turns"
    __table_args__ = (
        UniqueConstraint("game_id", "seq"),
        CheckConstraint(one_of("role", TurnRole), name="role_valid"),
    )

    id: Mapped[int] = _bigint_pk()
    game_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(SmallInteger)
    role: Mapped[str]
    content: Mapped[str]
    seller_turn: Mapped[dict[str, object] | None] = mapped_column(JSONB)  # SellerTurn output
    guards: Mapped[dict[str, object] | None] = mapped_column(JSONB)  # internal only, never shown
    trace_id: Mapped[str | None]
    created_at: Mapped[datetime] = _created_at()


class NegotiationEvent(Base):
    """Every decision taken by code (the MCP policy engine). Basis of the invalid-sale metrics."""

    __tablename__ = "negotiation_events"
    __table_args__ = (
        CheckConstraint(one_of("kind", EventKind), name="kind_valid"),
        CheckConstraint(
            f"decision IS NULL OR {one_of('decision', Decision)}", name="decision_valid"
        ),
        CheckConstraint(
            f"outcome IS NULL OR {one_of('outcome', CloseOutcome)}", name="outcome_valid"
        ),
        Index("ix_negotiation_events_game_id_turn", "game_id", "turn"),
    )

    id: Mapped[int] = _bigint_pk()
    game_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"))
    turn: Mapped[int] = mapped_column(SmallInteger)
    kind: Mapped[str]
    offer_usd: Mapped[int | None]
    decision: Mapped[str | None]
    counter_usd: Mapped[int | None]
    accepted_usd: Mapped[int | None]
    outcome: Mapped[str | None]
    reason_internal: Mapped[str | None]  # precise reason; NEVER returned to the LLM or clients
    created_at: Mapped[datetime] = _created_at()


class Deal(Base):
    """A closed sale. The primary key on game_id means at most one deal per game."""

    __tablename__ = "deals"
    __table_args__ = (CheckConstraint("price_usd > 0", name="price_positive"),)

    game_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), primary_key=True
    )
    price_usd: Mapped[int]
    idempotency_key: Mapped[uuid.UUID] = mapped_column(unique=True)
    closed_at: Mapped[datetime] = _created_at()


class LlmUsage(Base):
    """Token usage and estimated cost per LLM call. The daily budget gate sums this table."""

    __tablename__ = "llm_usage"
    __table_args__ = (
        CheckConstraint(one_of("component", LlmComponent), name="component_valid"),
        CheckConstraint("input_tokens >= 0 AND output_tokens >= 0", name="tokens_non_negative"),
        Index("ix_llm_usage_created_at", "created_at"),
    )

    id: Mapped[int] = _bigint_pk()
    game_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("games.id", ondelete="SET NULL"))
    component: Mapped[str]
    model_id: Mapped[str]
    input_tokens: Mapped[int]
    output_tokens: Mapped[int]
    est_cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    created_at: Mapped[datetime] = _created_at()
