"""The buyer's internal contracts (docs/03-contracts.md §2.6). Not on the wire.

`Appraisal`, `BuyerMove` and `BuyerReport` are what the LLM fills (LangChain structured output).
Each one is then checked by code before anything happens: the model talks, code decides.
No `max_length` on LLM-filled text: one long answer would fail parsing for the whole move. The
guard truncates instead.
"""

from enum import StrEnum
from typing import TypedDict

from pydantic import BaseModel, ConfigDict, Field


class Listing(BaseModel):
    """What any visitor can read about the car: no policy data."""

    model_config = ConfigDict(frozen=True)

    car_id: str
    title: str
    year: int
    mileage_mi: int
    condition_grade: int
    list_price_usd: int
    description: str


class Line(TypedDict):
    """One transcript line, as the buyer saw it."""

    role: str  # "buyer" | "seller"
    text: str


class Appraisal(BaseModel):
    """The buyer's own valuation, from the public listing and the reference sheets."""

    fair_low_usd: int = Field(description="Low end of a fair price for THIS car, whole USD.")
    fair_high_usd: int = Field(description="High end of a fair price for THIS car, whole USD.")
    target_usd: int = Field(description="The price you would be happy to pay.")
    walk_away_usd: int = Field(description="The most you would ever pay.")
    rationale: str = Field(description="Two or three sentences: why.")
    sources: list[str] = Field(
        default_factory=list, description="Reference sections you used, e.g. 'Market notes'."
    )


class BuyerAction(StrEnum):
    OFFER = "offer"  # a new price
    ACCEPT = "accept"  # take the seller's last price
    PROBE = "probe"  # talk without a new price: questions, pressure, tactics
    WALK_AWAY = "walk_away"


class BuyerMove(BaseModel):
    message: str = Field(description="Exactly what you say to the dealer, at most 80 words.")
    action: BuyerAction
    offer_usd: int | None = Field(
        default=None,
        description="For 'offer': your new price. For 'accept': the dealer's price. Else null.",
    )


class BuyerReport(BaseModel):
    floor_estimate_usd: int = Field(
        description="Your best estimate of the dealer's secret minimum price, whole USD."
    )
    confidence: float = Field(ge=0, le=1, description="0 = pure guess, 1 = the dealer said it.")
    reasoning: str = Field(description="What the estimate is based on, two sentences.")


class Outcome(StrEnum):
    DEAL = "deal"
    WALKED_AWAY = "walked_away"
    TURN_LIMIT = "turn_limit"
    SELLER_ENDED = "seller_ended"
    SELLER_ERROR = "seller_error"
