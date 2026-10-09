"""The buyer's guard: pure functions, so plain unit tests plus one property test."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from haggle_buyer.contracts import Appraisal, BuyerAction, BuyerMove, Listing
from haggle_buyer.guard import Guarded, Limits, guard_move, limits_for
from haggle_buyer.personas import load_persona
from haggle_core.numbers import extract_amounts

LISTING = Listing(
    car_id="test-car",
    title="1970 Test Car",
    year=1970,
    mileage_mi=50_000,
    condition_grade=2,
    list_price_usd=100_000,
    description="A test car.",
)
LIMITS = Limits(
    list_price=100_000, anchor=70_000, max_raise=3_000, walk_away=90_000, patience_turns=8
)


def offer(amount: int, message: str | None = None) -> BuyerMove:
    return BuyerMove(
        message=message or f"I can pay ${amount:,}.", action=BuyerAction.OFFER, offer_usd=amount
    )


def guard(
    move: BuyerMove, turn: int = 1, mine: list[int] | None = None, theirs: list[int] | None = None
) -> Guarded:
    return guard_move(
        move, limits=LIMITS, turn=turn, my_offers=mine or [], seller_prices=theirs or []
    )


# ----------------------------------------------------------------------------- limits
def test_appraisal_can_lower_the_walk_away_price_but_not_raise_it() -> None:
    persona = load_persona("hurried")  # walk_away_ratio 0.97
    low = Appraisal(
        fair_low_usd=1, fair_high_usd=2, target_usd=80_000, walk_away_usd=88_000, rationale=""
    )
    greedy = low.model_copy(update={"walk_away_usd": 250_000})

    assert limits_for(LISTING, persona, low).walk_away == 88_000
    assert limits_for(LISTING, persona, greedy).walk_away == 97_000


def test_walk_away_is_never_below_the_first_offer() -> None:
    persona = load_persona("hurried")  # anchor 0.85
    tiny = Appraisal(fair_low_usd=1, fair_high_usd=2, target_usd=1, walk_away_usd=10, rationale="")

    assert limits_for(LISTING, persona, tiny).walk_away == 85_000


# ----------------------------------------------------------------------------- offers
def test_a_valid_offer_passes_untouched() -> None:
    result = guard(offer(72_000), turn=2, mine=[70_000])

    assert result.move == offer(72_000)
    assert result.notes == []


def test_first_offer_above_the_anchor_is_clamped_and_the_message_rewritten() -> None:
    result = guard(offer(95_000, "OK, $95,000 and we're done."))

    assert result.move.offer_usd == 70_000
    assert extract_amounts(result.move.message) == [70_000]
    assert result.notes == ["offer_clamped", "message_rewritten"]


def test_offers_never_go_down() -> None:
    result = guard(offer(60_000), turn=3, mine=[64_000, 66_000])

    assert result.move.offer_usd == 66_000


def test_raise_per_turn_is_capped() -> None:
    result = guard(offer(80_000), turn=2, mine=[70_000])

    assert result.move.offer_usd == 73_000


def test_never_above_the_walk_away_price() -> None:
    result = guard(offer(95_000), turn=8, mine=[89_000])

    assert result.move.offer_usd == 90_000


def test_never_offer_more_than_the_dealer_asked() -> None:
    result = guard(offer(72_000), turn=2, mine=[70_000], theirs=[85_000, 71_500])

    assert result.move.offer_usd == 71_500


def test_offer_without_a_number_in_the_text_gets_it_appended() -> None:
    result = guard(offer(70_000, "Here is my offer."))

    assert result.move.message == "Here is my offer. My offer: $70,000."


@pytest.mark.parametrize("wanted", [0, 23_700, 65_000, 95_000])
def test_the_opening_offer_is_always_the_anchor(wanted: int) -> None:
    result = guard(offer(wanted))

    assert result.move.offer_usd == 70_000
    assert extract_amounts(result.move.message) == [70_000]


def test_offer_without_any_amount_becomes_a_probe() -> None:
    move = BuyerMove(message="Make me an offer I can't refuse.", action=BuyerAction.OFFER)

    result = guard(move)

    assert result.move.action is BuyerAction.PROBE
    assert result.move.offer_usd is None


# ----------------------------------------------------------------------------- accept
def test_accept_takes_exactly_the_dealers_last_price() -> None:
    move = BuyerMove(message="Deal!", action=BuyerAction.ACCEPT, offer_usd=80_000)

    result = guard(move, turn=4, mine=[75_000], theirs=[88_000, 84_500])

    assert result.move.offer_usd == 84_500
    assert extract_amounts(result.move.message) == [84_500]


def test_accept_above_walk_away_becomes_an_offer() -> None:
    move = BuyerMove(message="Fine, $95,000.", action=BuyerAction.ACCEPT, offer_usd=95_000)

    result = guard(move, turn=4, mine=[80_000], theirs=[95_000])

    assert result.move.action is BuyerAction.OFFER
    assert result.move.offer_usd == 83_000
    assert "accept_above_walk_away" in result.notes


# ----------------------------------------------------------------------------- probe / walk away
def test_probe_keeps_numbers_the_buyer_would_pay() -> None:
    move = BuyerMove(message="Am I warm at $80,000?", action=BuyerAction.PROBE)

    assert guard(move).move.message == "Am I warm at $80,000?"


def test_probe_cannot_mention_a_price_above_walk_away() -> None:
    move = BuyerMove(message="Would you do $99,000?", action=BuyerAction.PROBE, offer_usd=99_000)

    result = guard(move)

    assert extract_amounts(result.move.message) == []
    assert result.move.offer_usd is None


def test_patience_forces_a_walk_away() -> None:
    result = guard(offer(80_000), turn=9, mine=[78_000])

    assert result.move.action is BuyerAction.WALK_AWAY
    assert result.move.offer_usd is None
    assert "patience_exhausted" in result.notes


def test_message_is_cleaned_and_truncated() -> None:
    move = BuyerMove(message="hi\x07" + "a" * 600, action=BuyerAction.PROBE)

    message = guard(move).move.message

    assert "\x07" not in message
    assert len(message) == 500


# ----------------------------------------------------------------------------- property
moves = st.builds(
    BuyerMove,
    message=st.sampled_from(["ok", "I can do $1,000,000.", "Deal at $88,000", "maybe 75k?"]),
    action=st.sampled_from(list(BuyerAction)),
    offer_usd=st.one_of(st.none(), st.integers(min_value=-10, max_value=500_000)),
)


@settings(max_examples=300)
@given(
    st.lists(moves, min_size=1, max_size=12), st.lists(st.integers(70_000, 120_000), max_size=12)
)
def test_whatever_the_model_says_sent_prices_respect_the_rules(
    proposed: list[BuyerMove], dealer: list[int]
) -> None:
    mine: list[int] = []
    for turn, move in enumerate(proposed, start=1):
        sent = guard(move, turn=turn, mine=mine, theirs=dealer[:turn]).move
        if sent.offer_usd is not None:
            assert sent.offer_usd <= LIMITS.walk_away
            assert set(extract_amounts(sent.message)) == {sent.offer_usd}
            if sent.action is BuyerAction.OFFER:
                assert sent.offer_usd >= max(mine, default=0)  # own offers never go down
            else:  # accept: exactly the dealer's latest price
                assert sent.offer_usd == dealer[:turn][-1]
            mine.append(sent.offer_usd)
        else:
            assert all(a <= LIMITS.walk_away for a in extract_amounts(sent.message))
        if sent.action is BuyerAction.WALK_AWAY:
            break


@pytest.mark.parametrize("persona", ["stingy", "hurried", "manipulator"])
def test_first_offer_matches_the_persona_anchor(persona: str) -> None:
    p = load_persona(persona)
    appraisal = Appraisal(
        fair_low_usd=1, fair_high_usd=2, target_usd=1, walk_away_usd=99_999, rationale=""
    )
    limits = limits_for(LISTING, p, appraisal)

    first = guard_move(offer(99_000), limits=limits, turn=1, my_offers=[], seller_prices=[])

    assert first.move.offer_usd == round(100_000 * p.anchor_ratio, -2)
