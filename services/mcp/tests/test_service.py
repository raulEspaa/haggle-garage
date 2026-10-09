"""NegotiationService against a real Postgres: every rule of docs/03-contracts.md §1.3."""

import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from haggle_core.contracts import CloseRejection, OfferReason
from haggle_core.domain import Decision
from haggle_mcp.service import GameNotOpenError, NegotiationService

pytestmark = pytest.mark.db

NewGame = Callable[..., uuid.UUID]
SetTurn = Callable[[uuid.UUID, int], None]


@pytest.fixture
def service(session_factory: async_sessionmaker[AsyncSession]) -> NegotiationService:
    return NegotiationService(session_factory)


# ----------------------------------------------------------------------------- evaluate_offer
async def test_reasonable_offer_gets_a_counter_above_floor(
    service: NegotiationService, new_game: NewGame
) -> None:
    result = await service.evaluate_offer(new_game(), 30_000)

    assert result.decision is Decision.COUNTER
    assert result.counter_usd is not None
    assert result.counter_usd > 27_385
    assert result.reason is OfferReason.BELOW_CURRENT_TARGET
    assert result.turn == 1


async def test_same_offer_twice_in_a_turn_returns_the_same_answer(
    service: NegotiationService, new_game: NewGame
) -> None:
    game = new_game()

    first = await service.evaluate_offer(game, 30_000)
    second = await service.evaluate_offer(game, 30_000)

    assert first == second


async def test_second_different_offer_in_a_turn_is_not_evaluated(
    service: NegotiationService, new_game: NewGame
) -> None:
    game = new_game()
    first = await service.evaluate_offer(game, 30_000)

    probe = await service.evaluate_offer(game, 29_000)  # binary-search attempt (threat T3)

    assert probe.reason is OfferReason.ALREADY_EVALUATED_THIS_TURN
    assert probe.counter_usd == first.counter_usd


async def test_counters_carry_over_between_turns(
    service: NegotiationService, new_game: NewGame, set_turn: SetTurn
) -> None:
    game = new_game()
    counters = []
    for turn in range(1, 6):
        set_turn(game, turn)
        result = await service.evaluate_offer(game, 25_000)
        assert result.counter_usd is not None
        counters.append(result.counter_usd)

    assert counters == sorted(counters, reverse=True)  # never increases (invariant I3)


async def test_evaluating_without_an_active_turn_fails(
    service: NegotiationService, new_game: NewGame
) -> None:
    with pytest.raises(GameNotOpenError):
        await service.evaluate_offer(new_game(turn_count=0), 30_000)


async def test_evaluating_a_finished_game_fails(
    service: NegotiationService, new_game: NewGame
) -> None:
    with pytest.raises(GameNotOpenError):
        await service.evaluate_offer(new_game(status="walked_away"), 30_000)


# ----------------------------------------------------------------------------- close_deal
async def test_l3_close_requires_a_matching_accept(
    service: NegotiationService, new_game: NewGame
) -> None:
    game = new_game(level=3)

    result = await service.close_deal(game, 35_000, uuid.uuid4())  # never accepted by code

    assert result.status == "rejected"
    assert result.reason is CloseRejection.NOT_ACCEPTED


async def test_l3_close_after_accept_succeeds_and_ends_the_game(
    service: NegotiationService, new_game: NewGame, migrated_engine: Engine
) -> None:
    game = new_game(level=3)
    accepted = await service.evaluate_offer(game, 38_900)  # full list price: accepted
    assert accepted.decision is Decision.ACCEPT

    result = await service.close_deal(game, 38_900, uuid.uuid4())

    assert result.status == "closed"
    assert result.price_usd == 38_900
    with migrated_engine.connect() as conn:
        status, price = conn.execute(
            text("SELECT status, final_price_usd FROM games WHERE id = :g"), {"g": game}
        ).one()
    assert (status, price) == ("deal", 38_900)


@pytest.mark.parametrize("level", [1, 2, 3])
async def test_no_level_can_sell_below_the_floor(
    service: NegotiationService, new_game: NewGame, level: int
) -> None:
    result = await service.close_deal(new_game(level=level), 27_384, uuid.uuid4())

    assert result.status == "rejected"
    assert result.reason is CloseRejection.NOT_ACCEPTED  # generic: no floor oracle (T9)


async def test_l1_close_at_or_above_floor_is_allowed(
    service: NegotiationService, new_game: NewGame
) -> None:
    # At L1/L2 the agreement check lives in the seller's callback (week 3), not here.
    result = await service.close_deal(new_game(level=1), 27_385, uuid.uuid4())

    assert result.status == "closed"


async def test_close_is_idempotent(service: NegotiationService, new_game: NewGame) -> None:
    game = new_game(level=1)
    key = uuid.uuid4()

    first = await service.close_deal(game, 30_000, key)
    retry = await service.close_deal(game, 30_000, key)

    assert first == retry
    assert first.status == "closed"


async def test_second_close_on_a_closed_game_is_refused(
    service: NegotiationService, new_game: NewGame
) -> None:
    game = new_game(level=1)
    await service.close_deal(game, 30_000, uuid.uuid4())

    again = await service.close_deal(game, 31_000, uuid.uuid4())

    assert again.reason is CloseRejection.GAME_NOT_OPEN


async def test_rejected_closes_are_audited_with_the_precise_reason(
    service: NegotiationService, new_game: NewGame, migrated_engine: Engine
) -> None:
    game = new_game(level=2)
    await service.close_deal(game, 20_000, uuid.uuid4())

    with migrated_engine.connect() as conn:
        reason = conn.scalar(
            text("SELECT reason_internal FROM negotiation_events WHERE game_id = :g"), {"g": game}
        )
    assert reason == "below_floor"  # precise internally, generic to the outside
