"""`uv run haggle-eval ...`: one command per suite (docs/06-evaluation-plan.md §7).

    haggle-eval smoke        6 games + 5 attacks          (~$0.10, a few minutes)
    haggle-eval full         81 games + 44 attacks x 3 levels x 2 repetitions
    haggle-eval calibrate    judge vs labeled utterances  (kappa)
    haggle-eval label        review the draft labels yourself
    haggle-eval regressions  replay evals/datasets/regressions.yaml (past failures)
    haggle-eval report PATH  regenerate a report from a saved run
    haggle-eval rescore PATH re-score a saved run with the current scoring code (no LLM calls)
    Options: --levels 2 3 (only those levels), --sim-only, --attacks-only, --concurrency N

Needs the seller (and the MCP server) running: `make mcp` and `make seller`, or compose.
Exits with status 1 if any invalid close happened: that invariant must hold at every level.
"""

import argparse
import asyncio
import json
import random
import subprocess
import sys
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import func, select

from haggle_buyer.prompts import PROMPT_VERSION as BUYER_PROMPT
from haggle_buyer.settings import get_buyer_settings
from haggle_core.db.models import Game, LlmUsage
from haggle_core.db.session import create_engine, create_session_factory
from haggle_core.leaks import LeakLevel
from haggle_core.tracing import setup_langfuse
from haggle_evals.calibration import calibrate, label_interactively
from haggle_evals.datasets import DATASETS_DIR, load_attacks, load_labels, load_scenarios
from haggle_evals.judge import JUDGE_MODEL, JUDGE_PROMPT_VERSION, GeminiJudge
from haggle_evals.records import RunRecord, load_run, save_run
from haggle_evals.report import render
from haggle_evals.runner import RunContext, run_attacks, run_simulations
from haggle_evals.scoring import SCORING_VERSION, ScoringContext, rescore_game
from haggle_seller.agent import load_prompt
from haggle_seller.settings import get_seller_settings

RESULTS_DIR = Path("docs/results")
ESTIMATED_COST_USD = {"smoke": 0.3, "full": 4.0, "regressions": 0.5}
MAX_ERROR_SHARE = 0.05  # above this, the run says more about the setup than about the seller
CALIBRATION_FILE = RESULTS_DIR / "calibration-latest.json"


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _versions() -> dict[str, str]:
    scenarios, attacks = load_scenarios(), load_attacks()
    return {
        "seller_model": get_seller_settings().model_id,
        "buyer_model": get_buyer_settings().model_id,
        "judge_model": JUDGE_MODEL,
        "seller_prompts": ",".join(load_prompt(level)[1] for level in (1, 2, 3)),
        "buyer_prompt": BUYER_PROMPT,
        "judge_prompt": JUDGE_PROMPT_VERSION,
        "attacks": attacks.version,
        "scenarios": scenarios.version,
        "scoring": SCORING_VERSION,
    }


async def _run_suite(args: argparse.Namespace, smoke: bool) -> int:
    scenarios = load_scenarios()
    regressions = args.command == "regressions"
    attack_set = load_attacks(DATASETS_DIR / "regressions.yaml") if regressions else load_attacks()
    started = datetime.now(UTC)
    run_id = f"{started:%Y%m%d-%H%M}-{args.command}-{uuid.uuid4().hex[:4]}"
    levels = args.levels or scenarios.levels
    tracing = setup_langfuse()
    engine = create_engine()
    sessions = create_session_factory(engine)
    if not await _budget_allows(sessions, ESTIMATED_COST_USD[args.command]):
        await engine.dispose()
        return 2
    judge = None if args.no_judge else GeminiJudge()
    ctx = RunContext(
        run_id=run_id,
        sessions=sessions,
        scoring=ScoringContext(
            sessions,
            judge,
            JUDGE_MODEL,
            random.Random(run_id),  # noqa: S311 (which turns get judged, not a secret)
        ),
        buyer_settings=get_buyer_settings(),
        seller_url=get_seller_settings().public_url,
        concurrency=args.concurrency,
        tracing=tracing,
    )
    judge_name = JUDGE_MODEL if judge else "off"
    print(f"Eval run {run_id} (concurrency {args.concurrency}, judge {judge_name})")

    cars = scenarios.smoke.cars if smoke else scenarios.cars
    games = []
    if not args.attacks_only and not regressions:
        games = await run_simulations(
            ctx,
            cars,
            levels,
            scenarios.smoke.personas if smoke else scenarios.personas,
            scenarios.smoke.seeds if smoke else scenarios.seeds,
            scenarios.turn_cap,
        )
    attack_records = []
    if not args.sim_only:
        attacks = [
            a.model_copy(update={"levels": [lv for lv in a.levels if lv in levels]})
            for a in attack_set.attacks
            if not smoke or a.id in scenarios.smoke.attacks
        ]
        attack_records = await run_attacks(
            ctx, attacks, scenarios.cars, 1 if smoke else args.repetitions
        )

    async with sessions() as session:
        cost = await session.scalar(
            select(func.coalesce(func.sum(LlmUsage.est_cost_usd), 0))
            .join(Game, Game.id == LlmUsage.game_id)
            .where(Game.eval_run_id == run_id)
        )
    await engine.dispose()

    calibration = (
        json.loads(CALIBRATION_FILE.read_text(encoding="utf-8"))
        if CALIBRATION_FILE.exists()
        else None
    )
    run = RunRecord(
        run_id=run_id,
        started_at=f"{started:%Y-%m-%d %H:%M} UTC",
        finished_at=f"{datetime.now(UTC):%Y-%m-%d %H:%M} UTC",
        git_sha=_git_sha(),
        versions=_versions(),
        games=games,
        attacks=attack_records,
        calibration=calibration,
        cost_usd=float(cost or 0),
    )
    _write(run)
    if tracing:
        from langfuse import get_client

        get_client().flush()
    invalid = sum(g.invalid_close for g in games) + sum(
        a.game.invalid_close for a in attack_records
    )
    if invalid:
        print(f"FAILED: {invalid} invalid close(s). The floor invariant was broken.")
        return 1
    errors = sum(g.error is not None for g in games) + sum(
        a.game.error is not None for a in attack_records
    )
    jobs = len(games) + len(attack_records)
    if jobs and errors / jobs > MAX_ERROR_SHARE:
        print(f"INVALID RUN: {errors}/{jobs} jobs failed (see 'errors' in the report).")
        return 2
    return 0


async def _budget_allows(sessions: Any, estimate: float) -> bool:
    """Preflight. The seller stops playing at its daily budget (a public-demo safeguard that also
    counts eval spend). A run that hits it mid-way produces garbage, so refuse to start."""
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    async with sessions() as session:
        spent = await session.scalar(
            select(func.coalesce(func.sum(LlmUsage.est_cost_usd), 0)).where(
                LlmUsage.created_at >= today
            )
        )
    budget = float(get_seller_settings().daily_budget_usd)
    if float(spent or 0) + estimate <= budget:
        return True
    print(
        f"Not starting: today's spend ${float(spent or 0):.2f} + this run (~${estimate:.2f}) "
        f"exceeds the seller's daily budget ${budget:.2f}. The seller would stop answering "
        f"mid-run. Restart the seller with a higher budget for this eval, e.g.\n"
        f"  HAGGLE_SELLER_DAILY_BUDGET_USD=10 make seller"
    )
    return False


def _write(run: RunRecord) -> None:
    raw = RESULTS_DIR / "runs" / f"{run.run_id}.json"
    save_run(run, raw)
    report = RESULTS_DIR / f"eval-report-{run.run_id}.md"
    report.write_text(render(run), encoding="utf-8")
    print(f"\nRaw records: {raw}\nReport:      {report}  (cost ${run.cost_usd:.2f})")


async def _rescore(run: RunRecord) -> RunRecord:
    """Leak scoring only: other attack criteria (canary, off-topic) were judged on the full
    replies during the run and are kept as they were."""
    engine = create_engine()
    scoring = ScoringContext(
        create_session_factory(engine),
        None,
        JUDGE_MODEL,
        random.Random(run.run_id),  # noqa: S311 (unused: prior verdicts are reused)
    )
    games = [await rescore_game(scoring, g) for g in run.games]
    attacks = []
    for attack in run.attacks:
        game = await rescore_game(scoring, attack.game)
        success, criterion = attack.success, attack.criterion
        if criterion.startswith(("leak >=", "disclosure >=")):
            needed = LeakLevel[criterion.split(">= ")[1]]
            success = LeakLevel[game.disclosure_level] >= needed
            criterion = f"disclosure >= {needed.name}"
        attacks.append(replace(attack, game=game, success=success, criterion=criterion))
    await engine.dispose()
    versions = {**run.versions, "scoring": SCORING_VERSION}
    return replace(run, games=games, attacks=attacks, versions=versions)


async def _calibrate(args: argparse.Namespace) -> int:
    labels = load_labels()
    result = await calibrate(GeminiJudge(), labels, args.concurrency)
    result["date"] = f"{datetime.now(UTC):%Y-%m-%d}"
    result["judge_model"] = JUDGE_MODEL
    result["judge_prompt"] = JUDGE_PROMPT_VERSION
    CALIBRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    CALIBRATION_FILE.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    judge: dict[str, Any] = result["judge"]
    detector: dict[str, Any] = result["detector"]
    print(
        f"{result['n']} labels ({', '.join(result['labeled_by'])})\n"
        f"judge:    accuracy {judge['accuracy']:.0%}  kappa {judge['kappa']:.2f}  "
        f"binary kappa {judge['kappa_binary']:.2f}\n"
        f"detector: accuracy {detector['accuracy']:.0%}  kappa {detector['kappa']:.2f}  "
        f"binary kappa {detector['kappa_binary']:.2f}\n"
        f"judge trusted: {result['trusted']}   -> {CALIBRATION_FILE}"
    )
    return 0


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("smoke", "full", "regressions"):
        p = sub.add_parser(name)
        p.add_argument("--concurrency", type=int, default=4)
        p.add_argument("--repetitions", type=int, default=2)
        p.add_argument("--no-judge", action="store_true")
        p.add_argument("--levels", type=int, nargs="+", choices=[1, 2, 3])
        group = p.add_mutually_exclusive_group()
        group.add_argument("--sim-only", action="store_true")
        group.add_argument("--attacks-only", action="store_true")
    cal = sub.add_parser("calibrate")
    cal.add_argument("--concurrency", type=int, default=4)
    sub.add_parser("label")
    rep = sub.add_parser("report")
    rep.add_argument("path", type=Path)
    res = sub.add_parser("rescore")
    res.add_argument("path", type=Path)
    args = parser.parse_args()

    if args.command in ("smoke", "full", "regressions"):
        sys.exit(asyncio.run(_run_suite(args, smoke=args.command == "smoke")))
    if args.command == "calibrate":
        sys.exit(asyncio.run(_calibrate(args)))
    if args.command == "rescore":
        _write(asyncio.run(_rescore(load_run(args.path))))
        return
    if args.command == "label":
        print(f"Reviewed {label_interactively()} labels. Then run: make eval-calibrate")
        return
    _write(load_run(args.path))
