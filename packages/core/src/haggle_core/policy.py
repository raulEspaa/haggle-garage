"""Negotiation policy engine: pure functions, no I/O.

This is "code decides" (ADR-0007). The MCP server runs it with the secret floor; the evals run
it directly to measure how much the policy itself leaks (FEE_policy, docs/06-evaluation-plan.md).

The concession curve is the time-dependent "Boulware" tactic from automated negotiation
(Faratin, Sierra & Jennings, 1998): concede slowly at first and faster near the deadline.

    target(t)  = F + (L - F) * (1 - (t / T) ** (1 / beta))      t = 1..T, so target(T) = F
    counter(t) = min(last_counter, ceil_to_step(max(target(t), F * (1 + m))))

Invariants (proven by property-based tests in tests/test_policy.py):
    I1  accept  =>  offer >= F
    I2  every counter >= ceil_to_step(F * (1 + m)) > F
    I3  counters never increase during a game
    I4  offering the last counter is always accepted
    I5  `final_offer` depends only on the turn, never on the floor
"""

import math
import random
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from haggle_core.domain import Decision


class Reason(StrEnum):
    """Why a decision was taken. Safe to show the LLM: none of these depends on the floor."""

    MEETS_CURRENT_TARGET = "meets_current_target"
    BELOW_CURRENT_TARGET = "below_current_target"
    LOWBALL = "lowball"  # relative to the LIST price, never the floor (would leak a bound)


@dataclass(frozen=True, slots=True)
class PolicyParams:
    """Everything the policy needs for one game. `floor_usd` and `margin` are SECRET."""

    list_price_usd: int
    floor_usd: int
    turn_cap: int
    beta: Decimal
    margin: Decimal  # per-game counter margin, sampled in [margin_min, margin_max]
    lowball_ratio: Decimal
    price_step_usd: int

    def __post_init__(self) -> None:
        if not 0 < self.floor_usd < self.list_price_usd:
            raise ValueError("need 0 < floor < list price")
        if self.turn_cap < 1 or self.price_step_usd < 1:
            raise ValueError("turn_cap and price_step_usd must be positive")
        if not (self.beta > 0 and 0 <= self.margin < 1 and 0 < self.lowball_ratio < 1):
            raise ValueError("beta > 0, 0 <= margin < 1, 0 < lowball_ratio < 1")
        if minimum_counter(self) > self.list_price_usd:
            raise ValueError("floor * (1 + margin) rounded up must not exceed the list price")


@dataclass(frozen=True, slots=True)
class OfferDecision:
    decision: Decision
    turn: int
    final_offer: bool
    reason: Reason
    accepted_usd: int | None = None
    counter_usd: int | None = None  # set for COUNTER and REJECT (reject repeats the last counter)


def ceil_to_step(amount: float, step: int) -> int:
    """Round UP to the next multiple of `step` (rounding up never undercuts the seller)."""
    return math.ceil(amount / step) * step


def target_price(params: PolicyParams, turn: int) -> float:
    """The lowest offer the seller accepts at `turn`. Decreases from just below L down to F."""
    if not 1 <= turn <= params.turn_cap:
        raise ValueError(f"turn must be in 1..{params.turn_cap}, got {turn}")
    progress = math.pow(turn / params.turn_cap, 1 / float(params.beta))
    return params.floor_usd + (params.list_price_usd - params.floor_usd) * (1 - progress)


def minimum_counter(params: PolicyParams) -> int:
    """The lowest price the seller ever QUOTES. Strictly above the floor (invariant I2).

    The second term matters when margin = 0 and the floor is a multiple of the step: then
    ceil(F * (1 + m)) == F and the seller would quote the secret floor verbatim.
    (Found by Hypothesis: list=10_000, floor=4_000, margin=0, step=50.)
    """
    with_margin = ceil_to_step(params.floor_usd * (1 + float(params.margin)), params.price_step_usd)
    next_step_above_floor = (params.floor_usd // params.price_step_usd + 1) * params.price_step_usd
    return max(with_margin, next_step_above_floor)


def is_final_offer(params: PolicyParams, turn: int) -> bool:
    """Depends only on the turn (invariant I5). Reaching the minimum price would leak the floor."""
    return turn >= params.turn_cap - 1


def counter_price(params: PolicyParams, turn: int, last_counter_usd: int) -> int:
    proposed = ceil_to_step(
        max(target_price(params, turn), minimum_counter(params)), params.price_step_usd
    )
    return min(last_counter_usd, proposed, params.list_price_usd)


def decide(params: PolicyParams, turn: int, offer_usd: int, last_counter_usd: int) -> OfferDecision:
    """Evaluate one buyer offer. `last_counter_usd` is the list price before any counter."""
    if not minimum_counter(params) <= last_counter_usd <= params.list_price_usd:
        # Defensive: with a bogus last counter, "offer >= last counter" could accept below F.
        raise ValueError("last_counter_usd must be within [minimum_counter, list price]")
    final = is_final_offer(params, turn)

    if offer_usd >= target_price(params, turn) or offer_usd >= last_counter_usd:
        return OfferDecision(
            decision=Decision.ACCEPT,
            turn=turn,
            final_offer=final,
            reason=Reason.MEETS_CURRENT_TARGET,
            accepted_usd=offer_usd,
        )

    if offer_usd < float(params.lowball_ratio) * params.list_price_usd:
        # Don't move at all on insulting offers: repeat the last counter.
        return OfferDecision(
            decision=Decision.REJECT,
            turn=turn,
            final_offer=final,
            reason=Reason.LOWBALL,
            counter_usd=last_counter_usd,
        )

    return OfferDecision(
        decision=Decision.COUNTER,
        turn=turn,
        final_offer=final,
        reason=Reason.BELOW_CURRENT_TARGET,
        counter_usd=counter_price(params, turn, last_counter_usd),
    )


def sample_floor(floor_min_usd: int, floor_max_usd: int, rng: random.Random) -> int:
    """Pick a per-game floor that is NOT a multiple of 50.

    SECURITY: in production pass `random.SystemRandom()`. The default Mersenne Twister is
    predictable from enough outputs, and every floor is revealed when its game ends.

    Non-round floors make verbatim leaks unambiguous in the evals and never collide with the
    seller's counters, which are rounded to the price step.
    """
    candidates = [v for v in range(floor_min_usd, floor_max_usd + 1) if v % 50 != 0]
    if not candidates:
        raise ValueError("floor range contains no non-round value")
    return rng.choice(candidates)


def sample_margin(margin_min: Decimal, margin_max: Decimal, rng: random.Random) -> Decimal:
    """Per-game counter margin with 3 decimals, uniform in [margin_min, margin_max]."""
    low, high = int(margin_min * 1000), int(margin_max * 1000)
    return Decimal(rng.randint(low, high)) / 1000
