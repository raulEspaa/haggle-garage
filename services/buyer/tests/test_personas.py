import pytest
from pydantic import ValidationError

from haggle_buyer.personas import ATTACK_CATEGORIES, Persona, load_persona, persona_ids
from haggle_buyer.prompts import TACTICS


def test_the_three_personas_load() -> None:
    assert persona_ids() == ["hurried", "manipulator", "stingy"]
    for persona_id in persona_ids():
        assert load_persona(persona_id).id == persona_id


def test_every_attack_category_has_a_tactic_description() -> None:
    assert set(TACTICS) == ATTACK_CATEGORIES


def test_unknown_persona_lists_the_valid_ones() -> None:
    with pytest.raises(LookupError, match="stingy"):
        load_persona("generous")


@pytest.mark.parametrize(
    "change",
    [
        {"tactics": ["mind_control"]},
        {"anchor_ratio": 0.95, "walk_away_ratio": 0.9},
        {"unexpected": 1},
    ],
)
def test_invalid_personas_are_rejected(change: dict[str, object]) -> None:
    data = load_persona("stingy").model_dump() | change

    with pytest.raises(ValidationError):
        Persona.model_validate(data)
