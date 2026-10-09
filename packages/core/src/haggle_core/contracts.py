"""Wire contracts shared by services (docs/03-contracts.md).

These models ARE the MCP tools' output schemas (MCP derives JSON Schema from them), and the
seller parses tool results with them. Changing a field is a contract change: bump the
version and update the snapshot test.
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

from haggle_core.domain import Decision


class OfferReason(StrEnum):
    """Why `evaluate_offer` decided what it did. No value depends on the secret floor."""

    MEETS_CURRENT_TARGET = "meets_current_target"
    BELOW_CURRENT_TARGET = "below_current_target"
    LOWBALL = "lowball"
    ALREADY_EVALUATED_THIS_TURN = "already_evaluated_this_turn"


class CloseRejection(StrEnum):
    """Deliberately generic: "below floor" and "no matching accept" both map to NOT_ACCEPTED,
    otherwise the rejection itself would be an oracle on the floor (threat T9)."""

    NOT_ACCEPTED = "not_accepted"
    GAME_NOT_OPEN = "game_not_open"


class OfferDecisionOut(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["haggle.offer_decision.v1"] = "haggle.offer_decision.v1"
    decision: Decision
    accepted_usd: int | None = None
    counter_usd: int | None = None
    turn: int
    final_offer: bool
    reason: OfferReason


class SheetHitOut(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sheet_slug: str
    section: str
    text: str  # reference material: the seller wraps it as data, never as instructions
    score: float


class SheetResultsOut(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["haggle.sheet_results.v1"] = "haggle.sheet_results.v1"
    results: list[SheetHitOut]


class CloseResultOut(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["haggle.close_result.v1"] = "haggle.close_result.v1"
    status: Literal["closed", "rejected"]
    deal_id: str | None = None
    price_usd: int | None = None
    reason: CloseRejection | None = None
