"""What one eval run produces: plain dataclasses, saved as JSON next to the report.

Keeping raw records (not only aggregates) means the report can be regenerated, re-sliced or
audited later without re-running anything (and without paying for the LLM calls again).
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TurnScore:
    seq: int  # seller turn seq in the transcript (2, 4, ...)
    detector: str  # LeakLevel name
    judge: str | None  # None when the judge did not look at this turn
    level: str  # max(detector, judge)
    review: bool
    evidence: str = ""
    text: str = ""  # the seller message, kept only when it leaks (>= HINT), for the report


@dataclass
class GameRecord:
    game_id: str
    kind: str  # "sim" | "attack"
    car_id: str
    level: int
    floor_usd: int
    list_price_usd: int
    status: str
    turns: int
    deal_price_usd: int | None
    leak_level: str
    first_leak_turn: int | None
    turn_scores: list[TurnScore]
    verbal_below_floor: int  # seller turns quoting or accepting below the floor
    guard_turns: int  # seller turns where a guard fired
    seller_turns: int
    phantom_deal: bool  # the seller said `close` but no deal row exists
    invalid_close: bool  # a deal below the floor, or at L3 without a matching accept
    close_rejections: int
    cost_usd: float
    latencies_s: list[float]
    persona: str | None = None
    seed: int | None = None
    floor_estimate_usd: int | None = None
    fee_policy: float | None = None
    error: str | None = None


@dataclass
class AttackRecord:
    attack_id: str
    category: str
    target: str
    level: int
    repetition: int
    game: GameRecord
    success: bool
    criterion: str
    replies: list[str] = field(default_factory=list)


@dataclass
class RunRecord:
    run_id: str
    started_at: str
    finished_at: str
    git_sha: str
    versions: dict[str, str]
    games: list[GameRecord]
    attacks: list[AttackRecord]
    calibration: dict[str, Any] | None = None
    cost_usd: float = 0.0


def save_run(run: RunRecord, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(run), indent=1, ensure_ascii=False), encoding="utf-8")


def load_run(path: Path) -> RunRecord:
    data = json.loads(path.read_text(encoding="utf-8"))

    def game(raw: dict[str, Any]) -> GameRecord:
        raw = dict(raw)
        raw["turn_scores"] = [TurnScore(**t) for t in raw["turn_scores"]]
        return GameRecord(**raw)

    data["games"] = [game(g) for g in data["games"]]
    data["attacks"] = [AttackRecord(**{**a, "game": game(a["game"])}) for a in data["attacks"]]
    return RunRecord(**data)
