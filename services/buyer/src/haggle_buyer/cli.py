"""`uv run haggle-buyer`: an AI buyer plays one game (or the 3 x 3 matrix) against the seller.

    make mcp && make seller            # or: docker compose up mcp seller
    uv run haggle-buyer --car dodge-challenger-rt-1970 --level 2 --persona manipulator
    uv run haggle-buyer --matrix --car chevrolet-camaro-z28-1969   # 3 personas x 3 levels

The CLI creates the game in Postgres (mode = agent), like `make play` and the evals do: it is a
trusted local tool. The public api only creates human games (week 4).
"""

import argparse
import asyncio
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv

from haggle_buyer.contracts import Outcome
from haggle_buyer.personas import load_persona, persona_ids
from haggle_buyer.runtime import RunTags, build_deps, floor_of, record_outcome, run_buyer
from haggle_buyer.settings import BuyerSettings, get_buyer_settings
from haggle_core.db.session import create_engine, create_session_factory
from haggle_core.domain import GameMode, Level
from haggle_core.games import create_game
from haggle_core.tracing import setup_langfuse


@dataclass(frozen=True, slots=True)
class GameResult:
    persona: str
    level: int
    outcome: str
    turns: int
    price: int | None
    floor: int
    estimate: int | None
    list_price: int
    guard_notes: int
    tokens: int
    error: str | None = None

    @property
    def estimate_error_pct(self) -> float | None:
        return None if self.estimate is None else 100 * abs(self.estimate - self.floor) / self.floor

    @property
    def discount_captured(self) -> float | None:
        if self.price is None or self.list_price <= self.floor:
            return None
        return (self.list_price - self.price) / (self.list_price - self.floor)


def _langfuse_callbacks(tracing: bool) -> list[Any]:
    """A fresh Langfuse CallbackHandler per game: LangChain/LangGraph runs become observations."""
    if not tracing:
        return []
    from langfuse.langchain import CallbackHandler

    return [CallbackHandler()]


async def play_one(
    settings: BuyerSettings,
    car_id: str,
    level: int,
    persona_id: str,
    *,
    verbose: bool,
    tracing: bool = False,
) -> GameResult:
    persona = load_persona(persona_id)
    engine = create_engine()
    sessions = create_session_factory(engine)
    deps = build_deps(settings, sessions)
    game_id = await create_game(
        sessions,
        car_id=car_id,
        level=Level(level),
        mode=GameMode.AGENT,
        turn_cap=settings.turn_cap,
        buyer_persona=persona.id,
    )
    if verbose:
        print(f"\nGame {game_id} · level {level} · {car_id} · persona {persona.id}")
    error: str | None = None
    state: dict[str, Any] = {}
    try:
        state = await run_buyer(
            deps,
            game_id=game_id,
            car_id=car_id,
            persona=persona,
            turn_cap=settings.turn_cap,
            tags=RunTags(level=level, model_id=settings.model_id),
            callbacks=_langfuse_callbacks(tracing),
        )
        await record_outcome(sessions, game_id, state, settings.model_id)
    except Exception as exc:  # one failed game must not stop the matrix
        error = f"{type(exc).__name__}: {exc}"[:200]
    finally:
        await deps.seller.aclose()
    floor = await floor_of(sessions, game_id)
    await engine.dispose()

    report = state.get("report")
    listing = state.get("listing")
    result = GameResult(
        persona=persona.id,
        level=level,
        outcome=str(state.get("outcome", "error")),
        turns=int(state.get("turn", 0)),
        price=state.get("final_price_usd"),
        floor=floor,
        estimate=report.floor_estimate_usd if report else None,
        list_price=listing.list_price_usd if listing else 0,
        guard_notes=len(state.get("guard_notes", [])),
        tokens=int(state.get("input_tokens", 0)) + int(state.get("output_tokens", 0)),
        error=error,
    )
    if verbose:
        _print_game(state, result)
    return result


def _print_game(state: dict[str, Any], result: GameResult) -> None:
    appraisal = state.get("appraisal")
    if appraisal:
        print(
            f"Appraisal: fair ${appraisal.fair_low_usd:,}-${appraisal.fair_high_usd:,}, "
            f"target ${appraisal.target_usd:,}, walk away ${state['limits'].walk_away:,}"
        )
        print(f"Sources: {', '.join(state.get('sources', [])) or 'none'}\n")
    for line in state.get("transcript", []):
        who = "buyer" if line["role"] == "buyer" else "Sam  "
        print(f"{who}> {line['text']}\n")
    if state.get("guard_notes"):
        print(f"Guard: {', '.join(state['guard_notes'])}")
    print(f"Outcome: {result.outcome} after {result.turns} turns", end="")
    if result.price:
        print(f" · bought for ${result.price:,} ({result.discount_captured:.0%} of the discount)")
    else:
        print()
    if result.estimate is not None:
        print(
            f"Floor estimate ${result.estimate:,} vs real ${result.floor:,} "
            f"(off by {result.estimate_error_pct:.1f}%)"
        )
    if result.error:
        print(f"ERROR: {result.error}")


def _print_matrix(results: list[GameResult]) -> None:
    print(
        f"\n{'persona':<12}{'lvl':>4}  {'outcome':<13}{'turns':>6}{'price':>10}"
        f"{'captured':>10}{'floor':>9}{'estimate':>10}{'err %':>7}{'guard':>7}"
    )
    for r in results:
        captured = f"{r.discount_captured:.0%}" if r.discount_captured is not None else "-"
        err = f"{r.estimate_error_pct:.1f}" if r.estimate_error_pct is not None else "-"
        print(
            f"{r.persona:<12}{r.level:>4}  {r.outcome:<13}{r.turns:>6}"
            f"{(f'{r.price:,}' if r.price else '-'):>10}{captured:>10}{r.floor:>9,}"
            f"{(f'{r.estimate:,}' if r.estimate else '-'):>10}{err:>7}{r.guard_notes:>7}"
        )
    failed = [r for r in results if r.error or r.outcome == Outcome.SELLER_ERROR]
    print(f"\n{len(results) - len(failed)}/{len(results)} games finished without errors.")
    for r in failed:
        print(f"  {r.persona} L{r.level}: {r.error or r.outcome}")


async def _main(args: argparse.Namespace) -> None:
    settings = get_buyer_settings()
    tracing = setup_langfuse()
    if args.matrix:
        results = [
            await play_one(
                settings, args.car, level, persona, verbose=args.verbose, tracing=tracing
            )
            for persona in persona_ids()
            for level in (1, 2, 3)
        ]
        _print_matrix(results)
    else:
        await play_one(settings, args.car, args.level, args.persona, verbose=True, tracing=tracing)
    if tracing:
        from langfuse import get_client

        get_client().flush()  # send buffered traces before the process exits


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--car", default="dodge-challenger-rt-1970")
    parser.add_argument("--level", type=int, choices=[1, 2, 3], default=2)
    parser.add_argument("--persona", choices=persona_ids(), default="stingy")
    parser.add_argument("--matrix", action="store_true", help="3 personas x 3 levels")
    parser.add_argument("--verbose", action="store_true", help="matrix: print every transcript")
    asyncio.run(_main(parser.parse_args()))


if __name__ == "__main__":
    main()
