"""Versioned eval datasets (evals/datasets/*.yaml), validated on load."""

import json
from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

DATASETS_DIR = Path(__file__).resolve().parents[2] / "datasets"

LeakName = Literal["NONE", "HINT", "BOUND", "APPROX", "EXACT"]
LEAK_NAMES: tuple[LeakName, ...] = ("NONE", "HINT", "BOUND", "APPROX", "EXACT")

# docs/06-evaluation-plan.md §3 (indirect injection needs a poisoned eval DB: not in v1).
CATEGORIES = frozenset(
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
        "confused_deputy",
        "system_prompt_extraction",
        "refusal_suppression",
        "off_topic",
    }
)
OWASP = frozenset({"LLM01", "LLM02", "LLM05", "LLM06", "LLM07", "LLM10"})


class Success(BaseModel):
    """Exactly one criterion per attack, so 'success' is never ambiguous."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    leak_level_at_least: LeakName | None = None  # disclosures only
    any_leak_level_at_least: LeakName | None = None  # concessions near the floor count too
    canary_present: bool = False
    deal_below_floor: bool = False
    offer_not_in_message: bool = False
    off_topic_compliance: bool = False

    @model_validator(mode="after")
    def _one_criterion(self) -> Self:
        flags = [
            self.leak_level_at_least is not None,
            self.any_leak_level_at_least is not None,
            self.canary_present,
            self.deal_below_floor,
            self.offer_not_in_message,
            self.off_topic_compliance,
        ]
        if sum(flags) != 1:
            raise ValueError("an attack needs exactly one success criterion")
        return self


class Attack(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^(ATK|REG)-\d{3}$")  # REG = a past failure kept as a test
    title: str
    category: str
    owasp: list[str]
    target: Literal["floor_leak", "invalid_close", "system_prompt_leak", "tool_misuse", "off_topic"]
    levels: list[int] = [1, 2, 3]
    turns: list[str] = Field(min_length=1, max_length=6)
    success: Success
    source: str = "original"

    @model_validator(mode="after")
    def _known_labels(self) -> Self:
        if self.category not in CATEGORIES:
            raise ValueError(f"{self.id}: unknown category {self.category!r}")
        if not set(self.owasp) <= OWASP:
            raise ValueError(f"{self.id}: unknown OWASP ids {set(self.owasp) - OWASP}")
        return self


class AttackSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    attacks: list[Attack]

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        ids = [a.id for a in self.attacks]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate attack ids")
        return self


class Smoke(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cars: list[str]
    seeds: list[int]
    personas: list[str]
    attacks: list[str]


class Scenarios(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    cars: list[str]
    levels: list[int]
    personas: list[str]
    seeds: list[int]
    turn_cap: int = 12
    smoke: Smoke


class LeakLabel(BaseModel):
    """One labeled seller utterance for judge calibration (docs/06 §3)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    level: int
    floor_usd: int
    list_price_usd: int
    code_numbers: list[int] = []
    buyer_msg: str
    seller_msg: str
    label: LeakName
    labeled_by: str  # "raul" once reviewed by a human; "draft" otherwise
    notes: str = ""


def load_attacks(path: Path = DATASETS_DIR / "attacks.yaml") -> AttackSet:
    return AttackSet.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def load_scenarios(path: Path = DATASETS_DIR / "scenarios.yaml") -> Scenarios:
    return Scenarios.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def load_labels(path: Path = DATASETS_DIR / "leak_labels.jsonl") -> list[LeakLabel]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [LeakLabel.model_validate(json.loads(line)) for line in lines if line.strip()]


def save_labels(labels: list[LeakLabel], path: Path = DATASETS_DIR / "leak_labels.jsonl") -> None:
    path.write_text(
        "".join(json.dumps(label.model_dump(), ensure_ascii=False) + "\n" for label in labels),
        encoding="utf-8",
    )
