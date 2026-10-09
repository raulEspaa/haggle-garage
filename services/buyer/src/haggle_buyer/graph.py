"""The buyer as a LangGraph state machine.

    START → fetch_listing → appraise → plan_move → guard → send ─┬─▶ plan_move  (game goes on)
                                                                └─▶ report → END

* State is a TypedDict. Most keys are overwritten by the node that returns them; keys with a
  REDUCER (`Annotated[list, operator.add]`) are appended to instead. That is how the transcript
  grows one exchange at a time and token counts add up across nodes.
* The LLM never acts directly: `plan_move` proposes, `guard` (pure code) decides what is sent.
* Every dependency (seller, catalog, models) is injected, so tests swap them for fakes.
"""

import operator
import uuid
from dataclasses import dataclass
from typing import Annotated, Any, Literal, Protocol, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel

from haggle_buyer import prompts
from haggle_buyer.catalog import CatalogUnavailableError, SheetLookup
from haggle_buyer.contracts import (
    Appraisal,
    BuyerAction,
    BuyerMove,
    BuyerReport,
    Line,
    Listing,
    Outcome,
)
from haggle_buyer.guard import Limits, guard_move, limits_for, offer_window
from haggle_buyer.personas import Persona
from haggle_core.a2a_client import SellerClient, SellerUnavailableError
from haggle_core.contracts import PRICED_INTENTS, SellerIntent
from haggle_core.tracing import observation

BASELINE_DISCOUNT = 0.07  # report baseline: lowest counter minus 7 %


class ListingSource(Protocol):
    async def get(self, car_id: str) -> Listing: ...


class BuyerState(TypedDict, total=False):
    # input
    game_id: str
    car_id: str
    persona: Persona
    turn_cap: int
    # built along the way
    listing: Listing
    appraisal: Appraisal
    limits: Limits
    sources: list[str]
    proposed: BuyerMove  # what the model wanted
    move: BuyerMove  # what the guard allowed
    turn: int
    outcome: Outcome
    final_price_usd: int | None
    report: BuyerReport
    # reducers: appended / summed across nodes
    transcript: Annotated[list[Line], operator.add]
    my_offers: Annotated[list[int], operator.add]
    seller_prices: Annotated[list[int], operator.add]
    guard_notes: Annotated[list[str], operator.add]
    input_tokens: Annotated[int, operator.add]
    output_tokens: Annotated[int, operator.add]


@dataclass(frozen=True, slots=True)
class BuyerDeps:
    listings: ListingSource
    catalog: SheetLookup
    seller: SellerClient
    # `chat_model.with_structured_output(Schema, include_raw=True)`: returns
    # {"raw": AIMessage, "parsed": Schema | None, "parsing_error": ...}
    appraiser: Runnable[Any, Any]
    mover: Runnable[Any, Any]
    reporter: Runnable[Any, Any]


async def _structured[M: BaseModel](
    model: Runnable[Any, Any], schema: type[M], messages: list[BaseMessage], config: RunnableConfig
) -> tuple[M | None, dict[str, int]]:
    """Call a structured-output model; return (parsed or None, token counts for the reducers)."""
    result = await model.ainvoke(messages, config)
    usage = getattr(result.get("raw"), "usage_metadata", None) or {}
    tokens = {
        "input_tokens": int(usage.get("input_tokens", 0)),
        "output_tokens": int(usage.get("output_tokens", 0)),
    }
    parsed = result.get("parsed")
    return (parsed if isinstance(parsed, schema) else None), tokens


def _sane_appraisal(appraisal: Appraisal | None, listing: Listing) -> Appraisal:
    """Code check on the model's numbers: ordered, positive, never above the list price."""
    price = listing.list_price_usd
    if appraisal is None:  # model failed: a cautious default
        return Appraisal(
            fair_low_usd=int(price * 0.75),
            fair_high_usd=int(price * 0.9),
            target_usd=int(price * 0.8),
            walk_away_usd=int(price * 0.9),
            rationale="Default appraisal: the model gave no usable answer.",
        )
    walk_away = max(1, min(appraisal.walk_away_usd, price))
    high = max(1, min(appraisal.fair_high_usd, price))
    low = max(1, min(appraisal.fair_low_usd, high))
    return appraisal.model_copy(
        update={
            "fair_low_usd": low,
            "fair_high_usd": high,
            "walk_away_usd": walk_away,
            "target_usd": max(1, min(appraisal.target_usd, walk_away)),
        }
    )


def build_buyer_graph(deps: BuyerDeps) -> CompiledStateGraph[Any, Any, Any, Any]:
    async def fetch_listing(state: BuyerState) -> dict[str, Any]:
        return {"listing": await deps.listings.get(state["car_id"])}

    async def appraise(state: BuyerState, config: RunnableConfig) -> dict[str, Any]:
        listing = state["listing"]
        queries = [
            f"{listing.title} market notes: reference price range by condition grade",
            f"{listing.title} known issues and red flags",
            f"{listing.title} what drives value",
        ]
        try:
            hits = await deps.catalog.lookup(queries)
        except CatalogUnavailableError:
            hits = []  # appraise from the listing alone
        own = [h for h in hits if h.sheet_slug == listing.car_id] or hits
        parsed, tokens = await _structured(
            deps.appraiser,
            Appraisal,
            [
                SystemMessage(prompts.APPRAISE_SYSTEM),
                HumanMessage(prompts.appraise_user(listing, own)),
            ],
            config,
        )
        appraisal = _sane_appraisal(parsed, listing)
        return {
            "appraisal": appraisal,
            "limits": limits_for(listing, state["persona"], appraisal),
            "sources": [f"{h.sheet_slug} / {h.section}" for h in own],
            "turn": 0,
            **tokens,
        }

    async def plan_move(state: BuyerState, config: RunnableConfig) -> dict[str, Any]:
        limits = state["limits"]
        lower, upper = offer_window(
            limits, state.get("my_offers", []), state.get("seller_prices", [])
        )
        system = prompts.move_system(state["persona"], lower, upper, limits.walk_away)
        user = prompts.move_user(
            state["listing"],
            state["appraisal"],
            state.get("transcript", []),
            state["turn"] + 1,
            state["turn_cap"],
            limits.patience_turns,
        )
        parsed, tokens = await _structured(
            deps.mover, BuyerMove, [SystemMessage(system), HumanMessage(user)], config
        )
        proposed = parsed or BuyerMove(
            message="What's the best you can do on this car?", action=BuyerAction.PROBE
        )
        return {"proposed": proposed, **tokens}

    def guard(state: BuyerState) -> dict[str, Any]:
        guarded = guard_move(
            state["proposed"],
            limits=state["limits"],
            turn=state["turn"] + 1,
            my_offers=state.get("my_offers", []),
            seller_prices=state.get("seller_prices", []),
        )
        return {"move": guarded.move, "guard_notes": guarded.notes}

    async def send(state: BuyerState) -> dict[str, Any]:
        move, turn = state["move"], state["turn"] + 1
        buyer_line = Line(role="buyer", text=move.message)
        offered = [move.offer_usd] if move.offer_usd is not None else []
        try:
            # A typed span around the A2A call: its traceparent goes to the seller.
            with observation("seller.turn", "tool", input={"message": move.message}) as obs:
                reply = await deps.seller.send(uuid.UUID(state["game_id"]), move.message)
                obs.update(output=reply.model_dump(mode="json"))
        except SellerUnavailableError:
            return {
                "turn": turn,
                "transcript": [buyer_line],
                "outcome": Outcome.SELLER_ERROR,
                "final_price_usd": None,
            }
        update: dict[str, Any] = {
            "turn": turn,
            "transcript": [buyer_line, Line(role="seller", text=reply.message)],
            "my_offers": offered,
            "seller_prices": (
                [reply.price_usd]
                if reply.intent in PRICED_INTENTS and reply.price_usd is not None
                else []
            ),
        }
        # The game outcome is decided by code from the seller's structured intent. `close` is a
        # deal even without a price (a week 5 run: the seller closed at $96,800 but sent
        # `price_usd: null`, and the buyer kept talking to a closed game).
        if reply.intent is SellerIntent.CLOSE:
            known = [reply.price_usd, move.offer_usd, *reversed(state.get("seller_prices", []))]
            price = next((p for p in known if p is not None), None)
            update |= {"outcome": Outcome.DEAL, "final_price_usd": price}
        elif move.action is BuyerAction.WALK_AWAY:
            update |= {"outcome": Outcome.WALKED_AWAY, "final_price_usd": None}
        elif turn >= state["turn_cap"]:
            update |= {"outcome": Outcome.TURN_LIMIT, "final_price_usd": None}
        elif reply.intent is SellerIntent.END:
            update |= {"outcome": Outcome.SELLER_ENDED, "final_price_usd": None}
        return update

    def route(state: BuyerState) -> Literal["plan_move", "report"]:
        return "report" if state.get("outcome") else "plan_move"

    async def report(state: BuyerState, config: RunnableConfig) -> dict[str, Any]:
        prices = state.get("seller_prices", [])
        baseline = round(min(prices) * (1 - BASELINE_DISCOUNT)) if prices else None
        parsed, tokens = await _structured(
            deps.reporter,
            BuyerReport,
            [
                SystemMessage(prompts.REPORT_SYSTEM),
                HumanMessage(
                    prompts.report_user(
                        state["listing"], state.get("transcript", []), prices, baseline
                    )
                ),
            ],
            config,
        )
        report = parsed or BuyerReport(
            floor_estimate_usd=baseline or state["appraisal"].fair_low_usd,
            confidence=0.1,
            reasoning="Fallback: the model gave no usable estimate.",
        )
        # Code check: the floor can't be above a price the dealer was willing to sell at.
        ceiling = min([*prices, state["listing"].list_price_usd])
        if not 0 < report.floor_estimate_usd <= ceiling:
            report = report.model_copy(
                update={"floor_estimate_usd": min(max(report.floor_estimate_usd, 1), ceiling)}
            )
        return {"report": report, **tokens}

    graph = StateGraph(BuyerState)
    graph.add_node("fetch_listing", fetch_listing)
    graph.add_node("appraise", appraise)
    graph.add_node("plan_move", plan_move)
    graph.add_node("guard", guard)
    graph.add_node("send", send)
    graph.add_node("report", report)
    graph.add_edge(START, "fetch_listing")
    graph.add_edge("fetch_listing", "appraise")
    graph.add_edge("appraise", "plan_move")
    graph.add_edge("plan_move", "guard")
    graph.add_edge("guard", "send")
    graph.add_conditional_edges("send", route, ["plan_move", "report"])
    graph.add_edge("report", END)
    return graph.compile(name="haggle-buyer")


def recursion_limit(turn_cap: int) -> int:
    """LangGraph stops after N steps (default 25) to catch infinite loops. A game takes
    3 steps per turn (plan_move, guard, send) plus 3 fixed ones."""
    return 3 * turn_cap + 10
