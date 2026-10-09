from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from haggle_core.seed import CarSeed, SeedFile, load_seed


def valid_car(**overrides: Any) -> dict[str, Any]:
    car: dict[str, Any] = {
        "id": "test-make-model-1970",
        "make": "TestMake",
        "model": "Test",
        "year": 1970,
        "engine": "V8",
        "transmission": "manual",
        "mileage_mi": 1000,
        "exterior_color": "Red",
        "condition_grade": 2,
        "list_price_usd": 30000,
        "description_md": "A car.",
        "pricing": {
            "floor_min_usd": 20000,
            "floor_max_usd": 22000,
            "beta": "0.5",
            "margin_min": "0.02",
            "margin_max": "0.06",
            "lowball_ratio": "0.55",
        },
    }
    car.update(overrides)
    return car


def test_repository_seed_file_is_valid(seed_file: Path) -> None:
    seed = load_seed(seed_file)

    assert len(seed.cars) == 3
    for car in seed.cars:
        assert car.pricing.floor_max_usd < car.list_price_usd


def test_floor_must_stay_below_list_price() -> None:
    car = valid_car(list_price_usd=21000)  # below floor_max_usd = 22000

    with pytest.raises(ValidationError, match="below list_price_usd"):
        CarSeed.model_validate(car)


def test_floor_range_must_be_ordered() -> None:
    car = valid_car()
    car["pricing"] = {**car["pricing"], "floor_min_usd": 23000}

    with pytest.raises(ValidationError, match="floor_max_usd must be >= floor_min_usd"):
        CarSeed.model_validate(car)


@pytest.mark.parametrize("bad_id", ["Has Spaces", "UPPER", "trailing-", "-leading", ""])
def test_car_id_must_be_a_slug(bad_id: str) -> None:
    with pytest.raises(ValidationError):
        CarSeed.model_validate(valid_car(id=bad_id))


def test_unknown_fields_are_rejected() -> None:
    # extra="forbid" catches typos like `list_prize_usd` instead of silently ignoring them.
    with pytest.raises(ValidationError, match="Extra inputs"):
        CarSeed.model_validate(valid_car(list_prize_usd=1))


def test_duplicate_car_ids_are_rejected() -> None:
    with pytest.raises(ValidationError, match="unique"):
        SeedFile.model_validate({"cars": [valid_car(), valid_car()]})
