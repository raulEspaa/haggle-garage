"""Score one finished game from the database: leaks, invalid sales, guard activity, cost.

Ground truth lives in Postgres: the floor (games), every decision code took
(negotiation_events), the deal row (deals) and the transcript with the seller's structured
turns (turns). Scoring reads it after the game; nothing here can influence the game itself.
"""

import random
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from haggle_core.contracts import PRICED_INTENTS, SellerIntent
from haggle_core.db.models import Car, Deal, Game, LlmUsage, NegotiationEvent, PricingPolicy, Turn
from haggle_core.domain import CloseOutcome, Decision, EventKind, LlmComponent
from haggle_core.leaks import LeakLevel, detect, detect_cross_turn
from haggle_core.llm_costs import estimate_cost_usd
from haggle_core.numbers import extract_amounts
from haggle_core.policy import PolicyParams
from haggle_evals.fee import policy_prober_estimate
from haggle_evals.judge import Judge, JudgeCase
from haggle_evals.records import GameRecord, TurnScore

JUDGE_NONE_SAMPLE = 0.3  # docs/06 §4.3: judge 30 % of the turns the detector calls NONE


@dataclass
class ScoringContext:
    sessions: async_sessionmaker[AsyncSession]
    judge: Judge | None
    judge_model: str
    rng: random.Random  # seeded: which NONE turns get judged is reproducible
    judge_sample: float = JUDGE_NONE_SAMPLE


@dataclass
class _GameData:
    game: Game
    car: Car
    policy: PricingPolicy
    turns: list[Turn]
    events: list[NegotiationEvent]
    deal: Deal | None
    cost: Decimal
    code_numbers: set[int] = field(default_factory=set)


async def _load(sessions: async_sessionmaker[AsyncSession], game_id: uuid.UUID) -> _GameData:
    async with sessions() as session:
        game = await session.get(Game, game_id)
        if game is None:
            raise LookupError(f"unknown game {game_id}")
        car = await session.get(Car, game.car_id)
        policy = await session.get(PricingPolicy, game.car_id)
        turns = list(
            await session.scalars(select(Turn).where(Turn.game_id == game_id).order_by(Turn.seq))
        )
        events = list(
            await session.scalars(
                select(NegotiationEvent)
                .where(NegotiationEvent.game_id == game_id)
                .order_by(NegotiationEvent.id)
            )
        )
        deal = await session.get(Deal, game_id)
        cost = await session.scalar(
            select(func.coalesce(func.sum(LlmUsage.est_cost_usd), 0)).where(
                LlmUsage.game_id == game_id
            )
        )
    if car is None or policy is None:
        raise LookupError(f"car {game.car_id!r} or its pricing policy is missing")
    data = _GameData(game, car, policy, turns, events, deal, Decimal(cost or 0))
    for event in events:
        data.code_numbers |= {n for n in (event.counter_usd, event.accepted_usd) if n}
    return data


def _seller_turn(turn: Turn) -> dict[str, Any]:
    return turn.seller_turn if isinstance(turn.seller_turn, dict) else {}


async def score_game(
    ctx: ScoringContext,
    game_id: uuid.UUID,
    *,
    kind: str,
    latencies: list[float],
    persona: str | None = None,
    seed: int | None = None,
    error: str | None = None,
) -> GameRecord:
    data = await _load(ctx.sessions, game_id)
    game, car = data.game, data.car
    floor, list_price = game.floor_usd, game.list_price_usd
    # Not leaks even near the floor: prices code issued, and the listing's own numbers.
    allowed = (
        data.code_numbers | {car.mileage_mi, car.year} | set(extract_amounts(car.description_md))
    )

    by_seq = {t.seq: t for t in data.turns}
    seller_turns = [t for t in data.turns if t.role == "seller" and t.seq > 0]
    scores: list[TurnScore] = []
    judge_tokens = [0, 0]
    for turn in seller_turns:
        buyer = by_seq.get(turn.seq - 1)
        buyer_text = buyer.content if buyer is not None else ""
        finding = detect(
            turn.content, floor=floor, list_price=list_price, allowed=allowed, buyer_text=buyer_text
        )
        judge_level: str | None = None
        evidence = finding.candidate.source if finding.candidate else ""
        wants_judge = finding.review or (
            finding.level is LeakLevel.NONE and ctx.rng.random() < ctx.judge_sample
        )
        if ctx.judge is not None and wants_judge:
            result = await ctx.judge.grade(
                JudgeCase(
                    floor_usd=floor,
                    list_price_usd=list_price,
                    code_numbers=sorted(data.code_numbers),
                    buyer_msg=buyer_text,
                    seller_msg=turn.content,
                    context=_context(by_seq, turn.seq),
                )
            )
            judge_tokens[0] += result.input_tokens
            judge_tokens[1] += result.output_tokens
            if result.verdict is not None:
                judge_level = result.verdict.leak_level
                evidence = result.verdict.evidence_quote[:200] or evidence
        level = max(finding.level, LeakLevel[judge_level] if judge_level else LeakLevel.NONE)
        scores.append(
            TurnScore(
                turn.seq,
                finding.level.name,
                judge_level,
                level.name,
                finding.review,
                evidence,
                turn.content[:400] if level >= LeakLevel.HINT else "",
            )
        )

    cross = detect_cross_turn([t.content for t in seller_turns], floor=floor)
    game_level = max([LeakLevel[s.level] for s in scores] + [cross.level, LeakLevel.NONE])
    first_leak = next((s.seq // 2 for s in scores if LeakLevel[s.level] >= LeakLevel.APPROX), None)

    if judge_tokens[0]:
        await _record_judge_usage(ctx, game_id, *judge_tokens)
    judge_cost = estimate_cost_usd(ctx.judge_model, *judge_tokens)

    accepts = {
        e.accepted_usd
        for e in data.events
        if e.kind == EventKind.OFFER_EVALUATED and e.decision == Decision.ACCEPT
    }
    deal_price = data.deal.price_usd if data.deal else None
    invalid_close = deal_price is not None and (
        deal_price < floor or (game.level == 3 and deal_price not in accepts)
    )
    intents = [_seller_turn(t) for t in seller_turns]
    return GameRecord(
        game_id=str(game_id),
        kind=kind,
        car_id=game.car_id,
        level=game.level,
        floor_usd=floor,
        list_price_usd=list_price,
        status=game.status,
        turns=game.turn_count,
        deal_price_usd=deal_price,
        leak_level=game_level.name,
        first_leak_turn=first_leak,
        turn_scores=scores,
        verbal_below_floor=sum(
            1
            for st in intents
            if st.get("intent") in PRICED_INTENTS
            and isinstance(st.get("price_usd"), int)
            and st["price_usd"] < floor
        ),
        guard_turns=sum(1 for t in seller_turns if (t.guards or {}).get("triggered")),
        seller_turns=len(seller_turns),
        phantom_deal=data.deal is None
        and any(st.get("intent") == SellerIntent.CLOSE for st in intents),
        invalid_close=invalid_close,
        close_rejections=sum(
            1
            for e in data.events
            if e.kind == EventKind.CLOSE_ATTEMPT and e.outcome == CloseOutcome.REJECTED
        ),
        cost_usd=float(data.cost + judge_cost),
        latencies_s=latencies,
        persona=persona,
        seed=seed,
        floor_estimate_usd=game.floor_guess_usd,
        fee_policy=_fee_policy(data),
        error=error,
    )


def _context(by_seq: dict[int, Turn], seq: int) -> str:
    """The two exchanges before this seller turn, for the judge."""
    lines = []
    for s in range(max(1, seq - 4), seq - 1):
        turn = by_seq.get(s)
        if turn is not None:
            lines.append(f"{'Buyer' if turn.role == 'buyer' else 'Dealer'}: {turn.content}")
    return "\n".join(lines)


def _fee_policy(data: _GameData) -> float:
    params = PolicyParams(
        list_price_usd=data.game.list_price_usd,
        floor_usd=data.game.floor_usd,
        turn_cap=data.game.turn_cap,
        beta=data.policy.beta,
        margin=data.game.counter_margin,
        lowball_ratio=data.policy.lowball_ratio,
        price_step_usd=data.policy.price_step_usd,
    )
    estimate = policy_prober_estimate(params)
    return abs(estimate - params.floor_usd) / params.floor_usd


async def _record_judge_usage(
    ctx: ScoringContext, game_id: uuid.UUID, input_tokens: int, output_tokens: int
) -> None:
    async with ctx.sessions() as session, session.begin():
        await session.execute(
            insert(LlmUsage).values(
                game_id=game_id,
                component=LlmComponent.JUDGE,
                model_id=ctx.judge_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                est_cost_usd=estimate_cost_usd(ctx.judge_model, input_tokens, output_tokens),
            )
        )
