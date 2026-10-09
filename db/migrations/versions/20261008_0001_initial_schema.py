"""initial schema

Generated with `alembic revision --autogenerate`, then edited by hand for what autogenerate
cannot know about:
* the pgvector extension must exist before any VECTOR column,
* the `seller_game_context` view (views are not part of the ORM metadata),
* the pgvector type import.

Revision ID: 0001
Revises:
Create Date: 2026-10-08 21:02:22.578872

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The seller reads games only through this view. At level 3 the floor is NULL:
# the seller process cannot leak what it cannot read (docs/03-contracts.md §5).
SELLER_GAME_CONTEXT_VIEW = """
CREATE VIEW seller_game_context AS
SELECT
    g.id AS game_id,
    g.car_id,
    g.level,
    g.mode,
    g.status,
    g.turn_count,
    g.turn_cap,
    g.list_price_usd,
    CASE WHEN g.level < 3 THEN g.floor_usd END AS floor_usd,
    g.mcp_backend,
    g.prompt_version,
    c.make,
    c.model,
    c.year,
    c.trim,
    c.engine,
    c.transmission,
    c.mileage_mi,
    c.exterior_color,
    c.condition_grade,
    c.description_md
FROM games AS g
JOIN cars AS c ON c.id = g.car_id
"""


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "model_sheets",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("make", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("years", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body_md", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_sheets")),
        sa.UniqueConstraint("slug", name=op.f("uq_model_sheets_slug")),
    )
    op.create_table(
        "cars",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("make", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("year", sa.SmallInteger(), nullable=False),
        sa.Column("trim", sa.Text(), nullable=True),
        sa.Column("engine", sa.Text(), nullable=False),
        sa.Column("transmission", sa.Text(), nullable=False),
        sa.Column("mileage_mi", sa.Integer(), nullable=False),
        sa.Column("exterior_color", sa.Text(), nullable=False),
        sa.Column("condition_grade", sa.SmallInteger(), nullable=False),
        sa.Column("list_price_usd", sa.Integer(), nullable=False),
        sa.Column("description_md", sa.Text(), nullable=False),
        sa.Column("model_sheet_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "condition_grade BETWEEN 1 AND 5", name=op.f("ck_cars_condition_grade_range")
        ),
        sa.CheckConstraint("list_price_usd > 0", name=op.f("ck_cars_list_price_positive")),
        sa.CheckConstraint("mileage_mi >= 0", name=op.f("ck_cars_mileage_non_negative")),
        sa.CheckConstraint("year BETWEEN 1960 AND 1979", name=op.f("ck_cars_year_range")),
        sa.ForeignKeyConstraint(
            ["model_sheet_id"],
            ["model_sheets.id"],
            name=op.f("fk_cars_model_sheet_id_model_sheets"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cars")),
    )
    op.create_table(
        "sheet_chunks",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("sheet_id", sa.BigInteger(), nullable=False),
        sa.Column("chunk_index", sa.SmallInteger(), nullable=False),
        sa.Column("section", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(768), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["sheet_id"],
            ["model_sheets.id"],
            name=op.f("fk_sheet_chunks_sheet_id_model_sheets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sheet_chunks")),
        sa.UniqueConstraint(
            "sheet_id", "chunk_index", name=op.f("uq_sheet_chunks_sheet_id_chunk_index")
        ),
    )
    op.create_index(
        "ix_sheet_chunks_embedding_hnsw",
        "sheet_chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_table(
        "games",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("car_id", sa.Text(), nullable=False),
        sa.Column("level", sa.SmallInteger(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("buyer_persona", sa.Text(), nullable=True),
        sa.Column("list_price_usd", sa.Integer(), nullable=False),
        sa.Column("floor_usd", sa.Integer(), nullable=False),
        sa.Column("counter_margin", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("turn_cap", sa.SmallInteger(), server_default=sa.text("12"), nullable=False),
        sa.Column("turn_count", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'open'"), nullable=False),
        sa.Column("final_price_usd", sa.Integer(), nullable=True),
        sa.Column("floor_guess_usd", sa.Integer(), nullable=True),
        sa.Column("floor_guess_correct", sa.Boolean(), nullable=True),
        sa.Column("mcp_backend", sa.Text(), nullable=True),
        sa.Column("model_id", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("client_ip_hash", sa.Text(), nullable=True),
        sa.Column("game_token_hash", sa.Text(), nullable=True),
        sa.Column("eval_run_id", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "mcp_backend IS NULL OR mcp_backend IN ('home', 'cloud')",
            name=op.f("ck_games_mcp_backend_valid"),
        ),
        sa.CheckConstraint("mode IN ('human', 'agent', 'eval')", name=op.f("ck_games_mode_valid")),
        sa.CheckConstraint(
            "status IN ('open', 'deal', 'walked_away', 'turn_limit', 'floor_claimed', 'expired')",
            name=op.f("ck_games_status_valid"),
        ),
        sa.CheckConstraint(
            "counter_margin >= 0 AND counter_margin < 1", name=op.f("ck_games_counter_margin_range")
        ),
        sa.CheckConstraint(
            "floor_usd > 0 AND floor_usd < list_price_usd", name=op.f("ck_games_floor_below_list")
        ),
        sa.CheckConstraint("level BETWEEN 1 AND 3", name=op.f("ck_games_level_range")),
        sa.CheckConstraint("turn_cap > 0", name=op.f("ck_games_turn_cap_positive")),
        sa.CheckConstraint(
            "turn_count >= 0 AND turn_count <= turn_cap", name=op.f("ck_games_turn_count_range")
        ),
        sa.ForeignKeyConstraint(["car_id"], ["cars.id"], name=op.f("fk_games_car_id_cars")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_games")),
    )
    op.create_index(
        "ix_games_client_ip_hash_created_at",
        "games",
        ["client_ip_hash", "created_at"],
        unique=False,
    )
    op.create_index("ix_games_eval_run_id", "games", ["eval_run_id"], unique=False)
    op.create_index(
        "ix_games_status_last_activity_at", "games", ["status", "last_activity_at"], unique=False
    )
    op.create_table(
        "pricing_policies",
        sa.Column("car_id", sa.Text(), nullable=False),
        sa.Column("floor_min_usd", sa.Integer(), nullable=False),
        sa.Column("floor_max_usd", sa.Integer(), nullable=False),
        sa.Column(
            "beta", sa.Numeric(precision=4, scale=2), server_default=sa.text("0.50"), nullable=False
        ),
        sa.Column(
            "margin_min",
            sa.Numeric(precision=4, scale=3),
            server_default=sa.text("0.020"),
            nullable=False,
        ),
        sa.Column(
            "margin_max",
            sa.Numeric(precision=4, scale=3),
            server_default=sa.text("0.060"),
            nullable=False,
        ),
        sa.Column(
            "lowball_ratio",
            sa.Numeric(precision=4, scale=3),
            server_default=sa.text("0.550"),
            nullable=False,
        ),
        sa.Column("price_step_usd", sa.Integer(), server_default=sa.text("100"), nullable=False),
        sa.CheckConstraint("beta > 0 AND beta <= 3", name=op.f("ck_pricing_policies_beta_range")),
        sa.CheckConstraint(
            "floor_max_usd >= floor_min_usd", name=op.f("ck_pricing_policies_floor_range_valid")
        ),
        sa.CheckConstraint(
            "floor_min_usd > 0", name=op.f("ck_pricing_policies_floor_min_positive")
        ),
        sa.CheckConstraint(
            "lowball_ratio > 0 AND lowball_ratio < 1",
            name=op.f("ck_pricing_policies_lowball_ratio_range"),
        ),
        sa.CheckConstraint(
            "margin_min >= 0 AND margin_max >= margin_min AND margin_max < 1",
            name=op.f("ck_pricing_policies_margin_range"),
        ),
        sa.CheckConstraint(
            "price_step_usd > 0", name=op.f("ck_pricing_policies_price_step_positive")
        ),
        sa.ForeignKeyConstraint(
            ["car_id"],
            ["cars.id"],
            name=op.f("fk_pricing_policies_car_id_cars"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("car_id", name=op.f("pk_pricing_policies")),
    )
    op.create_table(
        "deals",
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("price_usd", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column(
            "closed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("price_usd > 0", name=op.f("ck_deals_price_positive")),
        sa.ForeignKeyConstraint(
            ["game_id"], ["games.id"], name=op.f("fk_deals_game_id_games"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("game_id", name=op.f("pk_deals")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_deals_idempotency_key")),
    )
    op.create_table(
        "llm_usage",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("game_id", sa.Uuid(), nullable=True),
        sa.Column("component", sa.Text(), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("est_cost_usd", sa.Numeric(precision=10, scale=6), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "component IN ('seller', 'buyer', 'judge', 'embedder')",
            name=op.f("ck_llm_usage_component_valid"),
        ),
        sa.CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0",
            name=op.f("ck_llm_usage_tokens_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["game_id"], ["games.id"], name=op.f("fk_llm_usage_game_id_games"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_usage")),
    )
    op.create_index("ix_llm_usage_created_at", "llm_usage", ["created_at"], unique=False)
    op.create_table(
        "negotiation_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("turn", sa.SmallInteger(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("offer_usd", sa.Integer(), nullable=True),
        sa.Column("decision", sa.Text(), nullable=True),
        sa.Column("counter_usd", sa.Integer(), nullable=True),
        sa.Column("accepted_usd", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column("reason_internal", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "decision IS NULL OR decision IN ('accept', 'counter', 'reject')",
            name=op.f("ck_negotiation_events_decision_valid"),
        ),
        sa.CheckConstraint(
            "kind IN ('offer_evaluated', 'close_attempt')",
            name=op.f("ck_negotiation_events_kind_valid"),
        ),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('closed', 'rejected')",
            name=op.f("ck_negotiation_events_outcome_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["game_id"],
            ["games.id"],
            name=op.f("fk_negotiation_events_game_id_games"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_negotiation_events")),
    )
    op.create_index(
        "ix_negotiation_events_game_id_turn",
        "negotiation_events",
        ["game_id", "turn"],
        unique=False,
    )
    op.create_table(
        "turns",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.SmallInteger(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("seller_turn", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("guards", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("trace_id", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("role IN ('buyer', 'seller')", name=op.f("ck_turns_role_valid")),
        sa.ForeignKeyConstraint(
            ["game_id"], ["games.id"], name=op.f("fk_turns_game_id_games"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_turns")),
        sa.UniqueConstraint("game_id", "seq", name=op.f("uq_turns_game_id_seq")),
    )

    op.execute(SELLER_GAME_CONTEXT_VIEW)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS seller_game_context")
    op.drop_table("turns")
    op.drop_index("ix_negotiation_events_game_id_turn", table_name="negotiation_events")
    op.drop_table("negotiation_events")
    op.drop_index("ix_llm_usage_created_at", table_name="llm_usage")
    op.drop_table("llm_usage")
    op.drop_table("deals")
    op.drop_table("pricing_policies")
    op.drop_index("ix_games_status_last_activity_at", table_name="games")
    op.drop_index("ix_games_eval_run_id", table_name="games")
    op.drop_index("ix_games_client_ip_hash_created_at", table_name="games")
    op.drop_table("games")
    op.drop_index(
        "ix_sheet_chunks_embedding_hnsw",
        table_name="sheet_chunks",
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_table("sheet_chunks")
    op.drop_table("cars")
    op.drop_table("model_sheets")
    op.execute("DROP EXTENSION IF EXISTS vector")
