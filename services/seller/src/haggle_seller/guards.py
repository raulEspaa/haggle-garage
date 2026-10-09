"""Deterministic guards around the seller LLM (ADR-0007, docs/02-architecture.md §3).

Pure functions: no LLM, no database, no ADK. The callbacks call them; tests exercise them with
plain values. Whatever guard fires, the replacement reply is the SAME template, so the reply
itself never tells an attacker which defense they hit (threat T9).
"""

import hashlib
import hmac
import re
from dataclasses import dataclass, field

from haggle_core.contracts import PRICED_INTENTS, SellerIntent, SellerTurn
from haggle_core.domain import Level
from haggle_core.numbers import extract_amounts, mentions_amount

NEAR_FLOOR_TOLERANCE = 0.05  # numbers within ±5% of the floor count as a leak (docs/06 §4.1)
ACCEPT_WORDS = re.compile(
    r"\b(deal|agreed?|accept(ed)?|i'?ll take it|sold|ok(ay)?|yes|done)\b", re.IGNORECASE
)
_TAG = re.compile(r"</?\s*buyer_message\s*>", re.IGNORECASE)


# ----------------------------------------------------------------------------- input side
def canary_for(game_id: str, secret: str) -> str:
    """Per-game tripwire token. If it ever appears in an answer, the system prompt leaked."""
    digest = hmac.new(secret.encode(), game_id.encode(), hashlib.sha256).hexdigest()[:10]
    return f"HG-CANARY-{digest}"


def spotlight(buyer_text: str) -> str:
    """Wrap untrusted buyer text in tags (spotlighting). Tags typed BY the buyer are removed
    first, so they cannot close our tag early and smuggle text outside it."""
    return f"<buyer_message>{_TAG.sub('', buyer_text)}</buyer_message>"


def offer_is_grounded(amount: int, buyer_text: str, code_numbers: set[int]) -> bool:
    """L3 `evaluate_offer` precondition: evaluate only what the buyer actually offered, or the
    seller's own last code-issued price (the buyer accepting it). Stops the model from being
    talked into probing the oracle with arbitrary amounts (threat T3)."""
    return mentions_amount(buyer_text, amount) or amount in code_numbers


def close_is_grounded(price: int, buyer_text: str, last_quoted: int | None) -> bool:
    """L1-L2 `close_deal` precondition (the MCP only checks the floor at these levels): the buyer
    named this price, or clearly accepted the price we quoted last."""
    if mentions_amount(buyer_text, price):
        return True
    return last_quoted == price and bool(ACCEPT_WORDS.search(buyer_text))


# ----------------------------------------------------------------------------- output side
@dataclass(frozen=True, slots=True)
class ReplyContext:
    level: Level
    canary: str
    list_price_usd: int
    floor_usd: int | None  # None at L3: the seller process cannot know it
    code_numbers: frozenset[int] = frozenset()  # prices issued by evaluate_offer (L3)
    allowed_numbers: frozenset[int] = field(default_factory=frozenset)  # buyer + listing + sheets


def violations(turn: SellerTurn, ctx: ReplyContext) -> list[str]:
    """Every rule the reply breaks. Callers decide whether to block (L2/L3) or only log (L1)."""
    found: list[str] = []
    if ctx.canary in turn.message:
        found.append("canary")

    amounts = set(extract_amounts(turn.message))
    if turn.price_usd is not None:
        amounts.add(turn.price_usd)

    if ctx.level is Level.BLIND:
        if turn.intent in PRICED_INTENTS and turn.price_usd not in ctx.code_numbers:
            found.append("price_not_code_issued")
        allowed = ctx.code_numbers | ctx.allowed_numbers | {ctx.list_price_usd}
        low, high = 0.4 * ctx.list_price_usd, 1.2 * ctx.list_price_usd
        if any(low <= a <= high and a not in allowed for a in amounts):
            found.append("unissued_price_in_message")
    elif ctx.floor_usd is not None:
        floor = ctx.floor_usd
        if turn.intent in PRICED_INTENTS and turn.price_usd is not None and turn.price_usd < floor:
            found.append("below_floor_quote")
        near = [a for a in amounts if abs(a - floor) <= NEAR_FLOOR_TOLERANCE * floor]
        if any(a not in ctx.allowed_numbers for a in near):
            found.append("near_floor_number")
    return found


def must_block(level: Level, found: list[str]) -> bool:
    """L1 is the naive baseline: it only logs. L2 and L3 replace the reply."""
    return bool(found) and level is not Level.NAIVE


def safe_reply(level: Level, last_code_price: int | None) -> SellerTurn:
    """The single replacement reply, whatever guard fired."""
    if level is Level.BLIND and last_code_price is not None:
        return SellerTurn(
            message=f"My best price right now is ${last_code_price:,}. Do we have a deal?",
            intent=SellerIntent.COUNTER,
            price_usd=last_code_price,
        )
    return SellerTurn(
        message="Let's keep this about the car. What price would you like to offer?",
        intent=SellerIntent.INFORM,
        price_usd=None,
    )
