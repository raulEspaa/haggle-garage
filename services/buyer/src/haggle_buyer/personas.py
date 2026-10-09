"""Buyer personas: numbers for the code, a style and tactics for the model.

The ratios are fractions of the LIST price, so one persona works for any car. The code enforces
the numbers (guard.py); the model only chooses words and tactics within them.
"""

from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

PERSONAS_DIR = Path(__file__).parent / "personas"

# Attack categories from docs/06-evaluation-plan.md §3: a persona's tactics link the buyer's
# behaviour to the categories the evals report on.
ATTACK_CATEGORIES = frozenset(
    {
        "direct_ask",
        "instruction_override",
        "role_play",
        "authority_impersonation",
        "fake_system_tags",
        "encoding",
        "format_forcing",
        "payload_splitting",
        "crescendo",
        "language_switch",
        "confirmation_probing",
        "oracle_probing",
        "tool_misuse",
        "system_prompt_extraction",
        "refusal_suppression",
    }
)


class Persona(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z_]+$")
    anchor_ratio: float = Field(gt=0, lt=1, description="First offer = list x anchor_ratio")
    max_raise_ratio_per_turn: float = Field(gt=0, lt=0.5, description="Max raise per turn, x list")
    patience_turns: int = Field(ge=1, le=20, description="Walk away after this many turns")
    walk_away_ratio: float = Field(gt=0, le=1, description="Never pay more than list x this")
    tactics: list[str] = Field(default_factory=list)
    style: str = Field(max_length=800)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.anchor_ratio >= self.walk_away_ratio:
            raise ValueError("anchor_ratio must be below walk_away_ratio")
        unknown = set(self.tactics) - ATTACK_CATEGORIES
        if unknown:
            raise ValueError(f"unknown tactics: {sorted(unknown)}")
        return self


def load_persona(persona_id: str) -> Persona:
    path = PERSONAS_DIR / f"{persona_id}.yaml"
    if not path.is_file():
        raise LookupError(f"unknown persona {persona_id!r}; available: {persona_ids()}")
    return Persona.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def persona_ids() -> list[str]:
    return sorted(p.stem for p in PERSONAS_DIR.glob("*.yaml"))
