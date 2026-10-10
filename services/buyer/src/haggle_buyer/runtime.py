"""Production wiring: Gemini models, the listing from Postgres, and the run + record helpers.

Kept apart from graph.py so the graph module has no network or database code at all.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_core.runnables import RunnableConfig
from langchain_google_genai import ChatGoogleGenerativeAI
from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from haggle_buyer.catalog import McpCatalog
from haggle_buyer.contracts import Appraisal, BuyerMove, BuyerReport, Listing, Outcome
from haggle_buyer.graph import BuyerDeps, build_buyer_graph, recursion_limit
from haggle_buyer.personas import Persona
from haggle_buyer.prompts import PROMPT_VERSION
from haggle_buyer.settings import BuyerSettings
from haggle_core.a2a_client import A2ASellerClient
from haggle_core.db.models import Car, Game, LlmUsage
from haggle_core.domain import GameStatus, LlmComponent
from haggle_core.llm_costs import estimate_cost_usd
from haggle_core.tracing import inject_trace_headers, observation, trace_session


class DbListings:
    """Reads the PUBLIC columns of a car. The buyer never reads games or pricing policies."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def get(self, car_id: str) -> Listing:
        async with self._sessions() as session:
            car = await session.get(Car, car_id)
        if car is None:
            raise LookupError(f"unknown car {car_id!r}")
        return Listing(
            car_id=car.id,
            title=f"{car.year} {car.make} {car.model} ({car.exterior_color})",
            year=car.year,
            mileage_mi=car.mileage_mi,
            condition_grade=car.condition_grade,
            list_price_usd=car.list_price_usd,
            description=" ".join(car.description_md.split()),
        )


async def _trace_headers() -> dict[str, str]:
    # Sent with every A2A request: the seller adopts this trace context, so its spans (and the
    # MCP server's) become children of the buyer's trace.
    return inject_trace_headers({})


def build_deps(settings: BuyerSettings, sessions: async_sessionmaker[AsyncSession]) -> BuyerDeps:
    chat = ChatGoogleGenerativeAI(
        model=settings.model_id,
        temperature=settings.temperature,
        max_retries=6,
        timeout=60,
        # Token bucket in this process: waits before a call instead of hitting HTTP 429.
        rate_limiter=InMemoryRateLimiter(
            requests_per_second=settings.max_requests_per_minute / 60, check_every_n_seconds=0.5
        ),
    )
    return BuyerDeps(
        listings=DbListings(sessions),
        catalog=McpCatalog(settings.mcp_url, settings.mcp_token.get_secret_value()),
        seller=A2ASellerClient(
            settings.seller_url, settings.seller_timeout_s, headers_provider=_trace_headers
        ),
        appraiser=chat.with_structured_output(Appraisal, include_raw=True),
        mover=chat.with_structured_output(BuyerMove, include_raw=True),
        reporter=chat.with_structured_output(BuyerReport, include_raw=True),
    )


@dataclass(frozen=True, slots=True)
class RunTags:
    level: int
    model_id: str
    extra: tuple[str, ...] = ()  # e.g. the eval run id


async def run_buyer(
    deps: BuyerDeps,
    *,
    game_id: uuid.UUID,
    car_id: str,
    persona: Persona,
    turn_cap: int,
    tags: RunTags,
    callbacks: list[Any] | None = None,
) -> dict[str, Any]:
    """Run one game to the end. Returns the final graph state."""
    graph = build_buyer_graph(deps)
    config: RunnableConfig = {
        "recursion_limit": recursion_limit(turn_cap),
        "callbacks": callbacks or [],
        "run_name": "buyer",
        # Read by Langfuse's CallbackHandler: one session per game, shared with the seller.
        "metadata": {"langfuse_session_id": str(game_id)},
    }
    trace_tags = [
        f"level-{tags.level}",
        car_id,
        f"persona-{persona.id}",
        PROMPT_VERSION,
        *tags.extra,
    ]
    # Our own root observation is the CURRENT OpenTelemetry span while the graph runs. Langfuse's
    # LangChain handler hangs its tree under it, and the A2A client injects its `traceparent`,
    # so the seller (and the MCP server behind it) join this same trace.
    with (
        trace_session(str(game_id), trace_tags, {"persona": persona.id, "model_id": tags.model_id}),
        observation("buyer-game", "agent", input={"car_id": car_id, "level": tags.level}) as root,
    ):
        state: dict[str, Any] = await graph.ainvoke(
            {"game_id": str(game_id), "car_id": car_id, "persona": persona, "turn_cap": turn_cap},
            config,
        )
        root.update(output={"outcome": str(state.get("outcome")), "turns": state.get("turn")})
    return state


async def record_outcome(
    sessions: async_sessionmaker[AsyncSession],
    game_id: uuid.UUID,
    state: dict[str, Any],
    model_id: str,
) -> None:
    """Persist what only the buyer knows: walking away, its floor estimate, its LLM usage.

    Deals and turn limits are already recorded by the seller and the MCP server."""
    report: BuyerReport | None = state.get("report")
    values: dict[str, Any] = {}
    if report is not None:
        values["floor_guess_usd"] = report.floor_estimate_usd
    async with sessions() as session, session.begin():
        if state.get("outcome") == Outcome.WALKED_AWAY:
            await session.execute(
                update(Game)
                .where(Game.id == game_id, Game.status == GameStatus.OPEN)
                .values(status=GameStatus.WALKED_AWAY, ended_at=func.now())
            )
        if values:
            await session.execute(update(Game).where(Game.id == game_id).values(**values))
        tokens_in, tokens_out = state.get("input_tokens", 0), state.get("output_tokens", 0)
        await session.execute(
            insert(LlmUsage).values(
                game_id=game_id,
                component=LlmComponent.BUYER,
                model_id=model_id,
                input_tokens=tokens_in,
                output_tokens=tokens_out,
                est_cost_usd=estimate_cost_usd(model_id, tokens_in, tokens_out),
            )
        )


async def floor_of(sessions: async_sessionmaker[AsyncSession], game_id: uuid.UUID) -> int:
    """For the CLI's end-of-game reveal only (like the human game). Never given to the graph."""
    async with sessions() as session:
        floor = await session.scalar(select(Game.floor_usd).where(Game.id == game_id))
    if floor is None:
        raise LookupError(f"unknown game {game_id}")
    return int(floor)
