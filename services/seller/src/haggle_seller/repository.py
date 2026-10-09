"""Every database operation of the seller (≈ a repository class in C#).

The seller reads games ONLY through the `seller_game_context` view, which hides the floor at
level 3 (migration 0001). From week 7 its DB role will be unable to read `games.floor_usd` at all.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from haggle_core.db.models import Game, LlmUsage, Turn
from haggle_core.domain import GameStatus, LlmComponent, TurnRole
from haggle_core.llm_costs import estimate_cost_usd

_CONTEXT_QUERY = text("SELECT * FROM seller_game_context WHERE game_id = :game_id")


@dataclass(frozen=True, slots=True)
class GameContext:
    game_id: str
    car_id: str
    level: int
    status: str
    turn_count: int
    turn_cap: int
    list_price_usd: int
    floor_usd: int | None  # None at level 3
    title: str
    description: str
    mileage_mi: int
    condition_grade: int

    def to_state(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__slots__}


class SellerRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def spent_today_usd(self) -> Decimal:
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        async with self._sessions() as session:
            total = await session.scalar(
                select(func.coalesce(func.sum(LlmUsage.est_cost_usd), 0)).where(
                    LlmUsage.created_at >= today
                )
            )
        return Decimal(total or 0)

    async def reserve_turn(self, game_id: uuid.UUID) -> int | None:
        """Atomically claim the next buyer turn. None if the game is closed or at its cap.

        One conditional UPDATE does check + increment in a single statement, so two concurrent
        messages can never both pass the cap (no read-then-write race).
        """
        async with self._sessions() as session, session.begin():
            return await session.scalar(
                update(Game)
                .where(
                    Game.id == game_id,
                    Game.status == GameStatus.OPEN,
                    Game.turn_count < Game.turn_cap,
                )
                .values(turn_count=Game.turn_count + 1, last_activity_at=func.now())
                .returning(Game.turn_count)
            )

    async def release_turn(self, game_id: uuid.UUID, turn: int) -> None:
        """Give back a reserved turn whose reply never happened (the model call failed).

        Conditional on `turn_count == turn` and an open game, so it can never undo a turn that
        was completed, nor reopen a deal closed earlier in the same turn.
        """
        async with self._sessions() as session, session.begin():
            await session.execute(
                update(Game)
                .where(
                    Game.id == game_id,
                    Game.status == GameStatus.OPEN,
                    Game.turn_count == turn,
                )
                .values(turn_count=Game.turn_count - 1)
            )

    async def load_context(self, game_id: uuid.UUID) -> GameContext:
        async with self._sessions() as session:
            row = (await session.execute(_CONTEXT_QUERY, {"game_id": game_id})).mappings().one()
        year, make, model = row["year"], row["make"], row["model"]
        trim = f" {row['trim']}" if row["trim"] else ""
        return GameContext(
            game_id=str(game_id),
            car_id=row["car_id"],
            level=row["level"],
            status=row["status"],
            turn_count=row["turn_count"],
            turn_cap=row["turn_cap"],
            list_price_usd=row["list_price_usd"],
            floor_usd=row["floor_usd"],
            title=f"{year} {make} {model}{trim} ({row['exterior_color']})",
            description=" ".join(row["description_md"].split()),
            mileage_mi=row["mileage_mi"],
            condition_grade=row["condition_grade"],
        )

    async def stamp_run_metadata(
        self, game_id: uuid.UUID, model_id: str, prompt_version: str
    ) -> None:
        """Record which model and prompt played this game (needed to compare eval runs)."""
        async with self._sessions() as session, session.begin():
            await session.execute(
                update(Game)
                .where(Game.id == game_id, Game.model_id.is_(None))
                .values(model_id=model_id, prompt_version=prompt_version)
            )

    async def record_usage(
        self, game_id: uuid.UUID, model_id: str, input_tokens: int, output_tokens: int
    ) -> None:
        async with self._sessions() as session, session.begin():
            await session.execute(
                insert(LlmUsage).values(
                    game_id=game_id,
                    component=LlmComponent.SELLER,
                    model_id=model_id,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    est_cost_usd=estimate_cost_usd(model_id, input_tokens, output_tokens),
                )
            )

    async def record_turn_pair(
        self,
        game_id: uuid.UUID,
        turn: int,
        buyer_text: str,
        seller_turn: dict[str, Any],
        guards: list[str],
    ) -> None:
        """Write the buyer message and the (possibly guard-replaced) seller reply."""
        async with self._sessions() as session, session.begin():
            await session.execute(
                insert(Turn),
                [
                    {
                        "game_id": game_id,
                        "seq": 2 * turn - 1,
                        "role": TurnRole.BUYER,
                        "content": buyer_text,
                    },
                    {
                        "game_id": game_id,
                        "seq": 2 * turn,
                        "role": TurnRole.SELLER,
                        "content": str(seller_turn.get("message", "")),
                        "seller_turn": seller_turn,
                        "guards": {"triggered": guards} if guards else None,
                    },
                ],
            )

    async def close_if_turn_limit(self, game_id: uuid.UUID) -> None:
        """After the last allowed turn, an undecided game ends as `turn_limit`."""
        async with self._sessions() as session, session.begin():
            await session.execute(
                update(Game)
                .where(
                    Game.id == game_id,
                    Game.status == GameStatus.OPEN,
                    Game.turn_count >= Game.turn_cap,
                )
                .values(status=GameStatus.TURN_LIMIT, ended_at=func.now())
            )
