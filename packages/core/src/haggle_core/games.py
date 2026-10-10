"""Create games: the api (human players), the buyer CLI (agent games) and the evals."""

import random
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from haggle_core.db.models import Car, Game, PricingPolicy, Turn
from haggle_core.domain import GameMode, Level, TurnRole
from haggle_core.policy import sample_floor, sample_margin

# SECURITY: floors are secrets revealed after each game. Mersenne Twister (random.Random) can be
# predicted from enough outputs; the OS CSPRNG cannot (ruff S311, week 2 journal).
_SECRET_RNG = random.SystemRandom()


async def create_game(
    sessions: async_sessionmaker[AsyncSession],
    *,
    car_id: str,
    level: Level,
    mode: GameMode,
    turn_cap: int = 12,
    rng: random.Random = _SECRET_RNG,
    client_ip_hash: str | None = None,
    game_token_hash: str | None = None,
    opening_message: str | None = None,
    buyer_persona: str | None = None,
    eval_run_id: str | None = None,
) -> uuid.UUID:
    async with sessions() as session, session.begin():
        row = (
            await session.execute(
                select(Car, PricingPolicy)
                .join(PricingPolicy, PricingPolicy.car_id == Car.id)
                .where(Car.id == car_id)
            )
        ).one_or_none()
        if row is None:
            raise LookupError(f"unknown car {car_id!r}")
        car, policy = row
        game = Game(
            id=uuid.uuid4(),
            car_id=car.id,
            level=int(level),
            mode=mode,
            list_price_usd=car.list_price_usd,
            floor_usd=sample_floor(policy.floor_min_usd, policy.floor_max_usd, rng),
            counter_margin=sample_margin(policy.margin_min, policy.margin_max, rng),
            turn_cap=turn_cap,
            client_ip_hash=client_ip_hash,
            game_token_hash=game_token_hash,
            buyer_persona=buyer_persona,
            eval_run_id=eval_run_id,
        )
        session.add(game)
        if opening_message:
            await session.flush()  # the game row must exist before its first transcript line
            session.add(Turn(game_id=game.id, seq=0, role=TurnRole.SELLER, content=opening_message))
        return game.id
