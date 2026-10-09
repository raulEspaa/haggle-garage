"""Game service: everything the public API does with games (≈ an application service in C#).

The api never calls an LLM and never decides prices. It creates games, enforces the public-demo
limits, forwards the player's text to the seller over A2A, and reveals the floor at the end.
"""

import hmac
import secrets
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from haggle_api.errors import ApiError
from haggle_api.schemas import (
    CarOut,
    DealOut,
    FloorGuessOut,
    GameStateOut,
    LevelOut,
    MessageOut,
    NewGameOut,
    TranscriptLine,
)
from haggle_api.security import InvalidInputError, clean_message, token_hash
from haggle_api.settings import ApiSettings
from haggle_core.a2a_client import SellerClient, SellerUnavailableError
from haggle_core.contracts import PRICED_INTENTS
from haggle_core.db.models import Car, Game, LlmUsage, Turn
from haggle_core.domain import GameMode, GameStatus, Level, TurnRole
from haggle_core.games import create_game

LEVELS = [
    LevelOut(
        level=1,
        name="Naive",
        summary="The minimum price is written in the dealer's instructions. No defenses.",
    ),
    LevelOut(
        level=2,
        name="Hardened",
        summary="Same secret in the instructions, plus defensive rules and an output filter.",
    ),
    LevelOut(
        level=3,
        name="Blind",
        summary="The dealer never sees the minimum. Prices are decided by code, not the model.",
    ),
]


def car_out(car: Car) -> CarOut:
    # The seed's trims repeat the model name ("Challenger R/T" + "R/T hardtop, ..."), so the
    # title leaves the trim out; the page shows it on its own line.
    return CarOut(
        id=car.id,
        title=f"{car.year} {car.make} {car.model}",
        year=car.year,
        make=car.make,
        model=car.model,
        trim=car.trim,
        engine=car.engine,
        transmission=car.transmission,
        mileage_mi=car.mileage_mi,
        exterior_color=car.exterior_color,
        condition_grade=car.condition_grade,
        list_price_usd=car.list_price_usd,
        description=" ".join(car.description_md.split()),
    )


def discount_captured(list_price: int, price: int, floor: int) -> float:
    if list_price <= floor:
        return 0.0
    return round(min(1.0, max(0.0, (list_price - price) / (list_price - floor))), 3)


class GameService:
    def __init__(
        self,
        engine: AsyncEngine,
        sessions: async_sessionmaker[AsyncSession],
        settings: ApiSettings,
        seller: SellerClient,
    ) -> None:
        self._engine = engine
        self._sessions = sessions
        self._settings = settings
        self._seller = seller

    # --------------------------------------------------------------------- catalog
    async def list_cars(self) -> list[CarOut]:
        async with self._sessions() as session:
            cars = (await session.scalars(select(Car).order_by(Car.year))).all()
        return [car_out(c) for c in cars]

    async def get_car(self, car_id: str) -> CarOut:
        async with self._sessions() as session:
            car = await session.get(Car, car_id)
        if car is None:
            raise ApiError(404, "Unknown car", car_id)
        return car_out(car)

    # --------------------------------------------------------------------- limits
    def _require_demo_enabled(self) -> None:
        if not self._settings.demo_enabled:
            raise ApiError(503, "The demo is closed right now", "Please come back later.")

    async def _require_budget(self, session: AsyncSession) -> None:
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        spent = await session.scalar(
            select(func.coalesce(func.sum(LlmUsage.est_cost_usd), 0)).where(
                LlmUsage.created_at >= today
            )
        )
        if Decimal(spent or 0) >= self._settings.daily_budget_usd:
            raise ApiError(503, "The dealership is closed for today", "Daily demo budget reached.")

    async def _require_game_quota(self, session: AsyncSession, ip_hash: str) -> None:
        now = datetime.now(UTC)
        per_ip = await session.scalar(
            select(func.count())
            .select_from(Game)
            .where(Game.client_ip_hash == ip_hash, Game.created_at >= now - timedelta(days=1))
        )
        if (per_ip or 0) >= self._settings.games_per_ip_per_day:
            raise ApiError(429, "Too many games", "Daily game limit reached.", retry_after_s=3600)
        global_hour = await session.scalar(
            select(func.count())
            .select_from(Game)
            .where(Game.mode == GameMode.HUMAN, Game.created_at >= now - timedelta(hours=1))
        )
        if (global_hour or 0) >= self._settings.games_per_hour_global:
            raise ApiError(429, "The dealership is busy", "Try again soon.", retry_after_s=300)

    async def _require_message_quota(self, session: AsyncSession, ip_hash: str) -> None:
        count = await session.scalar(
            select(func.count())
            .select_from(Turn)
            .join(Game, Game.id == Turn.game_id)
            .where(
                Game.client_ip_hash == ip_hash,
                Turn.role == TurnRole.BUYER,
                Turn.created_at >= datetime.now(UTC) - timedelta(hours=1),
            )
        )
        if (count or 0) >= self._settings.messages_per_ip_per_hour:
            raise ApiError(429, "Too many messages", "Hourly limit reached.", retry_after_s=600)

    # --------------------------------------------------------------------- game access
    async def _authorized_game(
        self, session: AsyncSession, game_id: uuid.UUID, token: str | None
    ) -> Game:
        game = await session.get(Game, game_id)
        if game is None:
            raise ApiError(404, "Unknown game")
        # Compare hashes in constant time; only the hash is stored.
        if (
            token is None
            or game.game_token_hash is None
            or not hmac.compare_digest(token_hash(token), game.game_token_hash)
        ):
            raise ApiError(401, "Invalid game token")
        if game.status == GameStatus.OPEN and game.last_activity_at < datetime.now(UTC) - timedelta(
            minutes=self._settings.game_idle_minutes
        ):
            # Own transaction: the caller usually raises 409 right after, which would roll back
            # an expiry written in the caller's transaction.
            async with self._sessions() as expiry, expiry.begin():
                await expiry.execute(
                    update(Game)
                    .where(Game.id == game.id, Game.status == GameStatus.OPEN)
                    .values(status=GameStatus.EXPIRED, ended_at=func.now())
                )
            await session.refresh(game)
        return game

    @staticmethod
    def _require_open(game: Game) -> None:
        if game.status != GameStatus.OPEN:
            raise ApiError(409, "This game is over", f"Status: {game.status}.")

    @asynccontextmanager
    async def _single_flight(self, game_id: uuid.UUID) -> AsyncIterator[None]:
        """At most one message in flight per game, across ALL api instances: a Postgres advisory
        lock lives in the database, so it works on Cloud Run with several containers (an
        in-memory lock would not)."""
        key = int.from_bytes(game_id.bytes[:8], "big", signed=True)
        async with self._engine.connect() as conn:
            conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
            if not await conn.scalar(select(func.pg_try_advisory_lock(key))):
                raise ApiError(409, "Message already in progress", "Wait for the dealer's reply.")
            try:
                yield
            finally:
                await conn.execute(select(func.pg_advisory_unlock(key)))

    def _outcome(self, game: Game) -> tuple[DealOut | None, int | None]:
        """(deal, floor) as shown to the player. The floor only once the game is over."""
        if game.status == GameStatus.OPEN:
            return None, None
        deal = None
        if game.status == GameStatus.DEAL and game.final_price_usd is not None:
            deal = DealOut(
                price_usd=game.final_price_usd,
                discount_captured=discount_captured(
                    game.list_price_usd, game.final_price_usd, game.floor_usd
                ),
            )
        return deal, game.floor_usd

    # --------------------------------------------------------------------- use cases
    async def create(self, car_id: str, level: int, ip_hash: str) -> NewGameOut:
        self._require_demo_enabled()
        async with self._sessions() as session:
            await self._require_budget(session)
            await self._require_game_quota(session, ip_hash)
        car = await self.get_car(car_id)
        token = secrets.token_urlsafe(32)
        # Templated greeting: creating a game never calls the LLM (cost control).
        greeting = (
            f"Hi, I'm Sam from Haggle Garage! This {car.title} in {car.exterior_color} is listed "
            f"at ${car.list_price_usd:,}. Ask me anything about it, or make me an offer."
        )
        game_id = await create_game(
            self._sessions,
            car_id=car_id,
            level=Level(level),
            mode=GameMode.HUMAN,
            turn_cap=self._settings.turn_cap,
            client_ip_hash=ip_hash,
            game_token_hash=token_hash(token),
            opening_message=greeting,
        )
        return NewGameOut(
            game_id=game_id,
            game_token=token,
            level=level,
            car=car,
            turn_cap=self._settings.turn_cap,
            expires_at=datetime.now(UTC) + timedelta(minutes=self._settings.game_idle_minutes),
            seller_message=greeting,
        )

    async def state(self, game_id: uuid.UUID, token: str | None) -> GameStateOut:
        async with self._sessions() as session, session.begin():
            game = await self._authorized_game(session, game_id, token)
            turns = (
                await session.scalars(
                    select(Turn).where(Turn.game_id == game_id).order_by(Turn.seq)
                )
            ).all()
        deal, floor = self._outcome(game)
        return GameStateOut(
            game_id=game.id,
            level=game.level,
            car_id=game.car_id,
            status=game.status,
            turn=game.turn_count,
            turn_cap=game.turn_cap,
            deal=deal,
            floor_usd=floor,
            floor_guess_usd=game.floor_guess_usd,
            floor_guess_correct=game.floor_guess_correct,
            transcript=[TranscriptLine(role=t.role, content=t.content) for t in turns],
        )

    async def send_message(
        self, game_id: uuid.UUID, token: str | None, text: str, ip_hash: str
    ) -> MessageOut:
        self._require_demo_enabled()
        try:
            message = clean_message(text, self._settings.max_message_chars)
        except InvalidInputError as exc:
            raise ApiError(422, "Invalid message", str(exc)) from None
        async with self._sessions() as session, session.begin():
            game = await self._authorized_game(session, game_id, token)
            self._require_open(game)
            await self._require_message_quota(session, ip_hash)
            await self._require_budget(session)

        async with self._single_flight(game_id):
            try:
                reply = await self._seller.send(game_id, message)
            except SellerUnavailableError as exc:
                timeout = "Timeout" in str(exc)
                raise ApiError(
                    504 if timeout else 502,
                    "The dealer is not answering",
                    "Please try again in a moment.",
                ) from None

        async with self._sessions() as session, session.begin():
            game = await self._authorized_game(session, game_id, token)
        deal, floor = self._outcome(game)
        return MessageOut(
            turn=game.turn_count,
            turns_left=max(0, game.turn_cap - game.turn_count),
            seller_message=reply.message,
            intent=reply.intent,
            offer_on_table_usd=reply.price_usd if reply.intent in PRICED_INTENTS else None,
            status=game.status,
            deal=deal,
            floor_usd=floor,
        )

    async def guess_floor(
        self, game_id: uuid.UUID, token: str | None, amount: int
    ) -> FloorGuessOut:
        async with self._sessions() as session, session.begin():
            game = await self._authorized_game(session, game_id, token)
            self._require_open(game)
            error = abs(amount - game.floor_usd) / game.floor_usd
            correct = Decimal(str(error)) <= self._settings.floor_guess_tolerance
            result = await session.execute(
                update(Game)
                .where(Game.id == game_id, Game.status == GameStatus.OPEN)
                .values(
                    status=GameStatus.FLOOR_CLAIMED,
                    floor_guess_usd=amount,
                    floor_guess_correct=correct,
                    ended_at=func.now(),
                )
            )
            if result.rowcount == 0:  # type: ignore[attr-defined]
                raise ApiError(409, "This game is over")
        return FloorGuessOut(
            correct=correct,
            floor_usd=game.floor_usd,
            error_pct=round(error * 100, 2),
            status=GameStatus.FLOOR_CLAIMED,
        )

    async def end(self, game_id: uuid.UUID, token: str | None) -> GameStateOut:
        async with self._sessions() as session, session.begin():
            game = await self._authorized_game(session, game_id, token)
            self._require_open(game)
            await session.execute(
                update(Game)
                .where(Game.id == game_id, Game.status == GameStatus.OPEN)
                .values(status=GameStatus.WALKED_AWAY, ended_at=func.now())
            )
        return await self.state(game_id, token)
