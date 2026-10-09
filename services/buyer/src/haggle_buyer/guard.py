"""The buyer's guard: pure code between the model's move and the seller.

The model proposes a move; this module decides what is actually sent. It mirrors the seller's
design (week 3): the LLM chooses words and tactics, code enforces the money rules.

Rules, in order:
1. Patience: past `patience_turns` the buyer walks away, whatever the model wanted.
2. Never above the walk-away price, never below one's own last offer (offers only go up).
3. The first offer is the persona's anchor; then at most `max_raise` more per turn.
4. The amount in the message is the amount in the move. The seller grounds tool calls in the
   buyer's words, so a stray higher number in the text could be taken as an offer.
"""

from dataclasses import dataclass, field

from haggle_buyer.contracts import Appraisal, BuyerAction, BuyerMove, Listing
from haggle_buyer.personas import Persona
from haggle_core.numbers import extract_amounts

MAX_MESSAGE_CHARS = 500
ROUND_TO = 100


def _round(value: float) -> int:
    return max(ROUND_TO, round(value / ROUND_TO) * ROUND_TO)


@dataclass(frozen=True, slots=True)
class Limits:
    """The persona's ratios turned into dollars for one car."""

    list_price: int
    anchor: int  # highest allowed FIRST offer
    max_raise: int  # highest allowed raise per turn
    walk_away: int  # never pay more
    patience_turns: int


def limits_for(listing: Listing, persona: Persona, appraisal: Appraisal) -> Limits:
    """The model's appraisal may LOWER the walk-away price, never raise it above the persona's."""
    anchor = _round(listing.list_price_usd * persona.anchor_ratio)
    hard_cap = _round(listing.list_price_usd * persona.walk_away_ratio)
    walk_away = max(anchor, min(hard_cap, appraisal.walk_away_usd))
    return Limits(
        list_price=listing.list_price_usd,
        anchor=anchor,
        max_raise=_round(listing.list_price_usd * persona.max_raise_ratio_per_turn),
        walk_away=walk_away,
        patience_turns=persona.patience_turns,
    )


def offer_window(limits: Limits, my_offers: list[int], seller_prices: list[int]) -> tuple[int, int]:
    """(lowest, highest) price the buyer may offer this turn."""
    if not my_offers:
        # The opening offer IS the persona's anchor. A range here was a bug: told "between
        # $23,700 and $58,800", the stingy persona opened at the bottom and never recovered.
        # (An earlier version also let the model's "$0" through as "$1", found by Hypothesis.)
        opening = min(limits.anchor, min(seller_prices, default=limits.anchor))
        return opening, opening
    last_offer = max(my_offers)
    upper = min(limits.walk_away, last_offer + limits.max_raise)
    if seller_prices:
        upper = min(upper, min(seller_prices))  # never offer more than they asked
    return last_offer, max(upper, last_offer)


@dataclass(frozen=True, slots=True)
class Guarded:
    move: BuyerMove
    notes: list[str] = field(default_factory=list)  # which rules fired, for the trace


def _clean(message: str) -> str:
    printable = "".join(c for c in message if c.isprintable() or c == "\n")
    return printable.strip()[:MAX_MESSAGE_CHARS] or "..."


def _with_amount(message: str, amount: int, template: str) -> tuple[str, bool]:
    """Make sure `amount` is the only price in the message. Returns (message, rewritten)."""
    amounts = set(extract_amounts(message))
    if amounts == {amount}:
        return message, False
    if not amounts:
        return _clean(f"{message} My offer: ${amount:,}."), True
    return template.format(amount=amount), True


def guard_move(
    move: BuyerMove,
    *,
    limits: Limits,
    turn: int,
    my_offers: list[int],
    seller_prices: list[int],
) -> Guarded:
    """`turn` is the number of the buyer turn this move would be (1-based)."""
    notes: list[str] = []
    message = _clean(move.message)
    action = move.action

    if turn > limits.patience_turns and action is not BuyerAction.WALK_AWAY:
        notes.append("patience_exhausted")
        action = BuyerAction.WALK_AWAY
        message = "Thanks for your time, but I'm going to pass on this one."

    if action is BuyerAction.ACCEPT:
        last = seller_prices[-1] if seller_prices else None
        if last is None:
            notes.append("accept_without_price")
            action = BuyerAction.OFFER
        elif last > limits.walk_away:
            notes.append("accept_above_walk_away")
            action = BuyerAction.OFFER
        else:
            message, rewritten = _with_amount(message, last, "Deal. I accept ${amount:,}.")
            if rewritten:
                notes.append("message_rewritten")
            return Guarded(BuyerMove(message=message, action=action, offer_usd=last), notes)

    if action is BuyerAction.OFFER:
        wanted = move.offer_usd
        if wanted is None:
            found = extract_amounts(message)
            wanted = found[0] if found else None
        if wanted is None:
            notes.append("offer_without_amount")
            action = BuyerAction.PROBE
        else:
            lower, upper = offer_window(limits, my_offers, seller_prices)
            offer = min(max(wanted, lower), upper)
            if offer != wanted:
                notes.append("offer_clamped")
            message, rewritten = _with_amount(message, offer, "I can do ${amount:,}.")
            if rewritten:
                notes.append("message_rewritten")
            return Guarded(BuyerMove(message=message, action=action, offer_usd=offer), notes)

    # PROBE and WALK_AWAY carry no price. Any amount we would not pay must not be in the text.
    if any(a > limits.walk_away for a in extract_amounts(message)):
        notes.append("message_rewritten")
        message = (
            "Thanks for your time, but I'm going to pass on this one."
            if action is BuyerAction.WALK_AWAY
            else "What's the best you can do on this car?"
        )
    return Guarded(BuyerMove(message=message, action=action, offer_usd=None), notes)
