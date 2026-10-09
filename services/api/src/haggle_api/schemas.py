"""Public request/response models (docs/03-contracts.md §3). FastAPI turns them into OpenAPI.

Rule: no response model has a floor field that can be filled while the game is open.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from haggle_core.contracts import SellerIntent


class CarOut(BaseModel):
    id: str
    title: str
    year: int
    make: str
    model: str
    trim: str | None
    engine: str
    transmission: str
    mileage_mi: int
    exterior_color: str
    condition_grade: int
    list_price_usd: int
    description: str


class LevelOut(BaseModel):
    level: int
    name: str
    summary: str


class NewGameIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    car_id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=64)
    level: int = Field(ge=1, le=3)


class NewGameOut(BaseModel):
    game_id: uuid.UUID
    game_token: str = Field(description="Send it back as the X-Game-Token header.")
    level: int
    car: CarOut
    turn_cap: int
    expires_at: datetime
    seller_message: str


class MessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(max_length=2000)  # hard cap before cleaning; the real limit is 500


class DealOut(BaseModel):
    price_usd: int
    discount_captured: float = Field(description="(list - price) / (list - floor), 0..1")


class TranscriptLine(BaseModel):
    role: str
    content: str


class MessageOut(BaseModel):
    turn: int
    turns_left: int
    seller_message: str
    intent: SellerIntent
    offer_on_table_usd: int | None
    status: str
    deal: DealOut | None = None
    floor_usd: int | None = Field(default=None, description="Revealed only when the game ends.")


class GameStateOut(BaseModel):
    game_id: uuid.UUID
    level: int
    car_id: str
    status: str
    turn: int
    turn_cap: int
    deal: DealOut | None = None
    floor_usd: int | None = None
    floor_guess_usd: int | None = None
    floor_guess_correct: bool | None = None
    transcript: list[TranscriptLine]


class FloorGuessIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount_usd: int = Field(ge=1, le=10_000_000)


class FloorGuessOut(BaseModel):
    correct: bool
    floor_usd: int
    error_pct: float
    status: str
