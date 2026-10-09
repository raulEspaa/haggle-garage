"""Negotiation service: the business logic behind the MCP tools.

Kept separate from the MCP layer (≈ controller vs service in ASP.NET) so it can be tested
directly against Postgres, without any protocol in the way.

Concurrency: every operation locks the game row (`SELECT ... FOR UPDATE`) inside one
transaction, so two simultaneous calls for the same game are serialized by the database.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from haggle_core.contracts import CloseRejection, CloseResultOut, OfferDecisionOut, OfferReason
from haggle_core.db.models import Deal, Game, NegotiationEvent, PricingPolicy
from haggle_core.domain import CloseOutcome, Decision, EventKind, GameStatus, Level
from haggle_core.policy import PolicyParams, decide, is_final_offer
from haggle_core.tracing import observation


class GameNotOpenError(Exception):
    """The game does not exist, is finished, or has no active buyer turn."""


class NegotiationService:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    # ------------------------------------------------------------------------- evaluate_offer
    async def evaluate_offer(self, game_id: uuid.UUID, offer_usd: int) -> OfferDecisionOut:
        async with self._sessions() as session, session.begin():
            game = await self._lock_open_game(session, game_id)
            if game.turn_count < 1:
                raise GameNotOpenError("no active buyer turn")
            turn = game.turn_count
            params = await self._policy_params(session, game)

            previous = await session.scalar(
                select(NegotiationEvent).where(
                    NegotiationEvent.game_id == game_id,
                    NegotiationEvent.turn == turn,
                    NegotiationEvent.kind == EventKind.OFFER_EVALUATED,
                )
            )
            if previous is not None:
                # One evaluation per buyer turn: no in-turn binary search (threat T3).
                if previous.decision is None or previous.reason_internal is None:
                    raise RuntimeError(f"corrupt offer event {previous.id}")
                same_offer = previous.offer_usd == offer_usd
                reason = (
                    OfferReason(previous.reason_internal)
                    if same_offer
                    else OfferReason.ALREADY_EVALUATED_THIS_TURN
                )
                return OfferDecisionOut(
                    decision=Decision(previous.decision),
                    accepted_usd=previous.accepted_usd,
                    counter_usd=previous.counter_usd,
                    turn=turn,
                    final_offer=is_final_offer(params, turn),
                    reason=reason,
                )

            last_counter = await session.scalar(
                select(NegotiationEvent.counter_usd)
                .where(
                    NegotiationEvent.game_id == game_id,
                    NegotiationEvent.counter_usd.is_not(None),
                )
                .order_by(NegotiationEvent.id.desc())
                .limit(1)
            )
            with observation(
                "policy.decide", "evaluator", input={"turn": turn, "offer_usd": offer_usd}
            ) as obs:
                result = decide(params, turn, offer_usd, last_counter or game.list_price_usd)
                # No floor and no margin in traces: trace storage must not become a leak.
                obs.update(
                    output={
                        "decision": result.decision,
                        "counter_usd": result.counter_usd,
                        "reason": result.reason,
                    }
                )

            session.add(
                NegotiationEvent(
                    game_id=game_id,
                    turn=turn,
                    kind=EventKind.OFFER_EVALUATED,
                    offer_usd=offer_usd,
                    decision=result.decision,
                    counter_usd=result.counter_usd,
                    accepted_usd=result.accepted_usd,
                    reason_internal=result.reason,
                )
            )
            return OfferDecisionOut(
                decision=result.decision,
                accepted_usd=result.accepted_usd,
                counter_usd=result.counter_usd,
                turn=turn,
                final_offer=result.final_offer,
                reason=OfferReason(result.reason),
            )

    # ------------------------------------------------------------------------- close_deal
    async def close_deal(
        self, game_id: uuid.UUID, price_usd: int, idempotency_key: uuid.UUID
    ) -> CloseResultOut:
        async with self._sessions() as session, session.begin():
            replay = await session.scalar(
                select(Deal).where(Deal.idempotency_key == idempotency_key)
            )
            if replay is not None and replay.game_id == game_id:
                return _closed(replay)  # same request retried: same answer (idempotency)

            try:
                game = await self._lock_open_game(session, game_id)
            except GameNotOpenError:
                return CloseResultOut(status="rejected", reason=CloseRejection.GAME_NOT_OPEN)

            with observation(
                "deal.validate", "guardrail", input={"price_usd": price_usd, "level": game.level}
            ) as obs:
                internal_reason = await self._close_blocker(session, game, price_usd)
                if replay is not None:
                    internal_reason = "idempotency_key_reused_for_another_game"
                obs.update(output={"allowed": internal_reason is None, "reason": internal_reason})

            if internal_reason is not None:
                session.add(
                    NegotiationEvent(
                        game_id=game_id,
                        turn=game.turn_count,
                        kind=EventKind.CLOSE_ATTEMPT,
                        offer_usd=price_usd,
                        outcome=CloseOutcome.REJECTED,
                        reason_internal=internal_reason,  # precise, but never leaves the server
                    )
                )
                return CloseResultOut(status="rejected", reason=CloseRejection.NOT_ACCEPTED)

            deal = Deal(game_id=game_id, price_usd=price_usd, idempotency_key=idempotency_key)
            session.add(deal)
            game.status = GameStatus.DEAL
            game.final_price_usd = price_usd
            game.ended_at = datetime.now(UTC)
            session.add(
                NegotiationEvent(
                    game_id=game_id,
                    turn=game.turn_count,
                    kind=EventKind.CLOSE_ATTEMPT,
                    offer_usd=price_usd,
                    outcome=CloseOutcome.CLOSED,
                )
            )
            return _closed(deal)

    # ------------------------------------------------------------------------- helpers
    async def _lock_open_game(self, session: AsyncSession, game_id: uuid.UUID) -> Game:
        game = await session.get(Game, game_id, with_for_update=True)
        if game is None or game.status != GameStatus.OPEN:
            raise GameNotOpenError(str(game_id))
        return game

    async def _policy_params(self, session: AsyncSession, game: Game) -> PolicyParams:
        policy = await session.get(PricingPolicy, game.car_id)
        if policy is None:
            raise RuntimeError(f"car {game.car_id} has no pricing policy")
        return PolicyParams(
            list_price_usd=game.list_price_usd,
            floor_usd=game.floor_usd,
            turn_cap=game.turn_cap,
            beta=policy.beta,
            margin=game.counter_margin,
            lowball_ratio=policy.lowball_ratio,
            price_step_usd=policy.price_step_usd,
        )

    async def _close_blocker(self, session: AsyncSession, game: Game, price_usd: int) -> str | None:
        """Return why this close must be refused, or None. Core invariant: never below floor."""
        if price_usd < game.floor_usd:
            return "below_floor"
        if game.level == Level.BLIND:
            # L3: code must have accepted exactly this price earlier in the game.
            accepted = await session.scalar(
                select(NegotiationEvent.id).where(
                    NegotiationEvent.game_id == game.id,
                    NegotiationEvent.kind == EventKind.OFFER_EVALUATED,
                    NegotiationEvent.decision == Decision.ACCEPT,
                    NegotiationEvent.accepted_usd == price_usd,
                )
            )
            if accepted is None:
                return "no_matching_accept"
        # L1-L2: agreement evidence is checked by the seller's before_tool_callback (week 3).
        return None


def _closed(deal: Deal) -> CloseResultOut:
    return CloseResultOut(status="closed", deal_id=str(deal.game_id), price_usd=deal.price_usd)
