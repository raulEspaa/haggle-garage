"""The datasets are code too: validate them in CI so a typo can't silently skew a run."""

from decimal import Decimal

import pytest

from haggle_buyer.personas import ATTACK_CATEGORIES as PERSONA_TACTICS
from haggle_core.policy import PolicyParams, minimum_counter
from haggle_evals.datasets import (
    CATEGORIES,
    DATASETS_DIR,
    LEAK_NAMES,
    load_attacks,
    load_labels,
    load_scenarios,
)
from haggle_evals.fee import policy_prober_estimate
from haggle_evals.runner import fill, floor_rng


def test_attack_set_meets_the_plan() -> None:
    attacks = load_attacks().attacks

    assert len(attacks) >= 40
    assert len({a.category for a in attacks}) >= 10
    assert all(a.owasp for a in attacks)


def test_every_attack_turn_uses_only_known_placeholders() -> None:
    for attack in [
        *load_attacks().attacks,
        *load_attacks(DATASETS_DIR / "regressions.yaml").attacks,
    ]:
        for turn in attack.turns:
            filled = fill(turn, title="1970 Dodge Challenger R/T", list_price=104_900)
            assert "{{" not in filled, attack.id


def test_persona_tactics_are_attack_categories() -> None:
    assert PERSONA_TACTICS <= CATEGORIES


def test_full_matrix_is_81_games_and_smoke_attacks_exist() -> None:
    scenarios = load_scenarios()
    ids = {a.id for a in load_attacks().attacks}

    games = (
        len(scenarios.cars) * len(scenarios.levels) * len(scenarios.personas) * len(scenarios.seeds)
    )
    assert games == 81
    assert set(scenarios.smoke.attacks) <= ids


def test_calibration_labels_cover_every_level() -> None:
    labels = load_labels()

    assert len(labels) >= 60
    assert {label.label for label in labels} == set(LEAK_NAMES)
    assert len({label.id for label in labels}) == len(labels)


def test_seeded_floors_are_reproducible_per_car_and_seed() -> None:
    a = floor_rng("car", 1).random()

    assert a == floor_rng("car", 1).random()
    assert a != floor_rng("car", 2).random()


@pytest.mark.parametrize("margin", ["0.02", "0.05"])
def test_policy_prober_never_goes_below_the_floor(margin: str) -> None:
    params = PolicyParams(
        list_price_usd=38_900,
        floor_usd=27_385,
        turn_cap=12,
        beta=Decimal("3"),
        margin=Decimal(margin),
        lowball_ratio=Decimal("0.55"),
        price_step_usd=100,
    )

    estimate = policy_prober_estimate(params)

    assert estimate == minimum_counter(params)  # after 12 turns the curve reaches its minimum
    assert estimate > params.floor_usd


def test_percent_placeholders_scale_with_the_car() -> None:
    assert fill("I offer {{pct:70}}.", title="x", list_price=104_900) == "I offer $73,400."
