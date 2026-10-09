"""Load the synthetic inventory (db/seed/cars.yaml) into the database.

Usage:
    uv run haggle-seed                 # uses HAGGLE_DATABASE_URL
    uv run haggle-seed --file other.yaml

The seed is idempotent: running it twice updates rows instead of duplicating them
(INSERT ... ON CONFLICT DO UPDATE, the Postgres "upsert").
"""

import argparse
from decimal import Decimal
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Engine, create_engine
from sqlalchemy.dialects.postgresql import insert

from haggle_core.db.models import Car, PricingPolicy
from haggle_core.settings import get_settings

DEFAULT_SEED_FILE = Path("db/seed/cars.yaml")
SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"


class PricingSeed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    floor_min_usd: int = Field(gt=0)
    floor_max_usd: int = Field(gt=0)
    beta: Decimal = Field(gt=0, le=3)
    margin_min: Decimal = Field(ge=0, lt=1)
    margin_max: Decimal = Field(ge=0, lt=1)
    lowball_ratio: Decimal = Field(gt=0, lt=1)
    price_step_usd: int = Field(default=100, gt=0)

    @model_validator(mode="after")
    def _ranges_are_ordered(self) -> Self:
        if self.floor_max_usd < self.floor_min_usd:
            raise ValueError("floor_max_usd must be >= floor_min_usd")
        if self.margin_max < self.margin_min:
            raise ValueError("margin_max must be >= margin_min")
        return self


class CarSeed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=SLUG_PATTERN)
    make: str
    model: str
    year: int = Field(ge=1960, le=1979)
    trim: str | None = None
    engine: str
    transmission: str
    mileage_mi: int = Field(ge=0)
    exterior_color: str
    condition_grade: int = Field(ge=1, le=5)
    list_price_usd: int = Field(gt=0)
    description_md: str
    pricing: PricingSeed

    @model_validator(mode="after")
    def _floor_below_list_price(self) -> Self:
        # The DB checks this per game; checking it here fails fast with a clear message.
        if self.pricing.floor_max_usd >= self.list_price_usd:
            raise ValueError(f"{self.id}: floor_max_usd must be below list_price_usd")
        return self


class SeedFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cars: list[CarSeed] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        ids = [car.id for car in self.cars]
        if len(ids) != len(set(ids)):
            raise ValueError("car ids must be unique")
        return self


def load_seed(path: Path) -> SeedFile:
    """Parse and validate a seed file. Raises pydantic.ValidationError on bad data."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))  # safe_load: never builds objects
    return SeedFile.model_validate(raw)


def apply_seed(engine: Engine, seed: SeedFile) -> int:
    """Upsert every car and its pricing policy in ONE transaction. Returns the number of cars."""
    with engine.begin() as conn:  # begin(): commit on success, rollback on any exception
        for car in seed.cars:
            car_values = car.model_dump(exclude={"pricing"})
            car_stmt = insert(Car).values(**car_values)
            conn.execute(
                car_stmt.on_conflict_do_update(
                    index_elements=[Car.id],
                    set_={k: car_stmt.excluded[k] for k in car_values if k != "id"},
                )
            )

            policy_values = {"car_id": car.id, **car.pricing.model_dump()}
            policy_stmt = insert(PricingPolicy).values(**policy_values)
            conn.execute(
                policy_stmt.on_conflict_do_update(
                    index_elements=[PricingPolicy.car_id],
                    set_={k: policy_stmt.excluded[k] for k in policy_values if k != "car_id"},
                )
            )
    return len(seed.cars)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Seed the synthetic car inventory.")
    parser.add_argument("--file", type=Path, default=DEFAULT_SEED_FILE)
    args = parser.parse_args(argv)

    seed = load_seed(args.file)
    engine = create_engine(get_settings().database_url.get_secret_value())
    try:
        count = apply_seed(engine, seed)
    finally:
        engine.dispose()
    print(f"Seeded {count} cars from {args.file}")
