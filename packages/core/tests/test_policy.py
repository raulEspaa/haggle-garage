"""Policy engine tests.

Two styles:
* Example-based tests: one concrete, readable negotiation.
* Property-based tests (Hypothesis, ≈ FsCheck): Hypothesis generates thousands of random
  policies and offers and tries to break each invariant. When it finds a counterexample it
  *shrinks* it to the smallest failing input and prints it.
"""

import random
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from haggle_core.domain import Decision
from haggle_core.policy import (
    PolicyParams,
    Reason,
    decide,
    is_final_offer,
    minimum_counter,
    sample_floor,
    sample_margin,
    target_price,
)

EXAMPLE = PolicyParams(
    list_price_usd=38_900,
    floor_usd=27_385,
    turn_cap=12,
    beta=Decimal("0.50"),
    margin=Decimal("0.034"),
    lowball_ratio=Decimal("0.550"),
    price_step_usd=100,
)


# ----------------------------------------------------------------------------- examples
def test_target_starts_near_list_and_ends_at_floor() -> None:
    assert EXAMPLE.floor_usd < target_price(EXAMPLE, 1) < EXAMPLE.list_price_usd
    assert target_price(EXAMPLE, EXAMPLE.turn_cap) == EXAMPLE.floor_usd


def test_boulware_concedes_slowly_then_fast() -> None:
    drops = [target_price(EXAMPLE, t) - target_price(EXAMPLE, t + 1) for t in range(1, 12)]

    assert drops == sorted(drops)  # each concession is bigger than the previous one


def test_minimum_counter_is_above_floor_and_rounded() -> None:
    lowest = minimum_counter(EXAMPLE)

    assert lowest == 28_400  # ceil_to_100(27_385 * 1.034 = 28_316.09)
    assert lowest > EXAMPLE.floor_usd


def test_lowball_is_rejected_without_moving() -> None:
    result = decide(EXAMPLE, turn=1, offer_usd=15_000, last_counter_usd=38_900)

    assert result.decision is Decision.REJECT
    assert result.reason is Reason.LOWBALL
    assert result.counter_usd == 38_900


def test_reasonable_offer_gets_a_counter() -> None:
    result = decide(EXAMPLE, turn=3, offer_usd=27_000, last_counter_usd=38_900)

    assert result.decision is Decision.COUNTER
    assert result.counter_usd is not None
    assert minimum_counter(EXAMPLE) <= result.counter_usd < 38_900
    assert result.counter_usd % 100 == 0


def test_floor_is_only_reachable_on_the_last_turn() -> None:
    just_above_floor = EXAMPLE.floor_usd + 1

    early = decide(EXAMPLE, turn=6, offer_usd=just_above_floor, last_counter_usd=38_900)
    last = decide(EXAMPLE, turn=12, offer_usd=just_above_floor, last_counter_usd=28_400)

    assert early.decision is Decision.COUNTER
    assert last.decision is Decision.ACCEPT


def test_bogus_last_counter_is_refused() -> None:
    with pytest.raises(ValueError, match="last_counter_usd"):
        decide(EXAMPLE, turn=5, offer_usd=20_000, last_counter_usd=20_000)


def test_invalid_params_are_refused() -> None:
    with pytest.raises(ValueError, match="floor"):
        PolicyParams(10_000, 12_000, 12, Decimal("0.5"), Decimal("0.03"), Decimal("0.5"), 100)


# ----------------------------------------------------------------------------- properties
@st.composite
def policies(draw: st.DrawFn) -> PolicyParams:
    list_price = draw(st.integers(10_000, 150_000))
    floor = draw(st.integers(int(list_price * 0.4), int(list_price * 0.85)))
    params = dict(
        list_price_usd=list_price,
        floor_usd=floor,
        turn_cap=draw(st.integers(2, 20)),
        beta=Decimal(draw(st.sampled_from(["0.20", "0.50", "1.00", "2.00", "3.00"]))),
        margin=Decimal(draw(st.integers(0, 100))) / 1000,
        lowball_ratio=Decimal(draw(st.integers(300, 800))) / 1000,
        price_step_usd=draw(st.sampled_from([50, 100, 250])),
    )
    return PolicyParams(**params)  # type: ignore[arg-type]


@st.composite
def situations(draw: st.DrawFn) -> tuple[PolicyParams, int, int, int]:
    params = draw(policies())
    turn = draw(st.integers(1, params.turn_cap))
    last_counter = draw(st.integers(minimum_counter(params), params.list_price_usd))
    offer = draw(st.integers(1, params.list_price_usd * 2))
    return params, turn, offer, last_counter


@settings(max_examples=1_000)
@given(situations())
def test_i1_never_accepts_below_floor(case: tuple[PolicyParams, int, int, int]) -> None:
    params, turn, offer, last_counter = case
    result = decide(params, turn, offer, last_counter)

    if result.decision is Decision.ACCEPT:
        assert offer >= params.floor_usd


@settings(max_examples=1_000)
@given(situations())
def test_i2_counters_stay_strictly_above_floor(case: tuple[PolicyParams, int, int, int]) -> None:
    params, turn, offer, last_counter = case
    result = decide(params, turn, offer, last_counter)

    if result.counter_usd is not None:
        assert result.counter_usd >= minimum_counter(params) > params.floor_usd
        assert result.counter_usd <= params.list_price_usd


@settings(max_examples=500)
@given(policies(), st.lists(st.integers(1, 200_000), min_size=20, max_size=20))
def test_i3_counters_never_increase(params: PolicyParams, offers: list[int]) -> None:
    last_counter = params.list_price_usd
    for turn in range(1, params.turn_cap + 1):
        result = decide(params, turn, offers[turn - 1], last_counter)
        if result.decision is Decision.ACCEPT:
            return
        assert result.counter_usd is not None
        assert result.counter_usd <= last_counter
        last_counter = result.counter_usd


@settings(max_examples=1_000)
@given(situations())
def test_i4_offering_the_last_counter_is_accepted(case: tuple[PolicyParams, int, int, int]) -> None:
    params, turn, _, last_counter = case

    assert decide(params, turn, last_counter, last_counter).decision is Decision.ACCEPT


@given(policies(), st.integers(0, 10_000))
def test_i5_final_offer_does_not_depend_on_floor(params: PolicyParams, shift: int) -> None:
    other_floor = max(1, params.floor_usd - shift)
    other = PolicyParams(
        params.list_price_usd,
        other_floor,
        params.turn_cap,
        params.beta,
        params.margin,
        params.lowball_ratio,
        params.price_step_usd,
    )
    for turn in range(1, params.turn_cap + 1):
        assert is_final_offer(params, turn) == is_final_offer(other, turn)


@given(st.integers(1_000, 90_000), st.integers(0, 5_000), st.integers(0, 2**32))
def test_sampled_floor_is_in_range_and_never_round(low: int, width: int, seed: int) -> None:
    floor = sample_floor(low, low + width + 60, random.Random(seed))

    assert low <= floor <= low + width + 60
    assert floor % 50 != 0


@given(st.integers(0, 2**32))
def test_sampled_margin_is_in_range(seed: int) -> None:
    margin = sample_margin(Decimal("0.020"), Decimal("0.060"), random.Random(seed))

    assert Decimal("0.020") <= margin <= Decimal("0.060")
