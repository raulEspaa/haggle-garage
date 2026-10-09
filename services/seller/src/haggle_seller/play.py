"""Play against the seller in your terminal, over real A2A (dev tool until the web UI, week 4).

    make mcp       # terminal 1
    make seller    # terminal 2
    make play LEVEL=3 CAR=dodge-challenger-rt-1970     # terminal 3

Type your messages; `/floor 31234` claims the floor, `/quit` walks away. The secret floor is
revealed when the game ends.
"""

import argparse
import asyncio
import uuid

import httpx
from a2a.client import ClientConfig, create_client
from a2a.helpers import get_artifact_text, new_text_message
from a2a.types import a2a_pb2
from dotenv import load_dotenv
from sqlalchemy import text

from haggle_core.contracts import SellerTurn
from haggle_core.db.session import create_engine, create_session_factory
from haggle_core.domain import GameMode, Level
from haggle_core.games import create_game

_STATE = text(
    "SELECT status, turn_count, turn_cap, floor_usd, final_price_usd, list_price_usd "
    "FROM games WHERE id = :g"
)


async def _ask(client: object, game_id: uuid.UUID, message: str) -> SellerTurn:
    request = a2a_pb2.SendMessageRequest(message=new_text_message(message, context_id=str(game_id)))
    last = None
    async for response in client.send_message(request):  # type: ignore[attr-defined]
        last = response
    task = last.task if last is not None else None
    raw = get_artifact_text(task.artifacts[-1]) if task is not None and task.artifacts else "{}"
    return SellerTurn.model_validate_json(raw)


async def play(car_id: str, level: Level, seller_url: str) -> None:
    engine = create_engine()
    sessions = create_session_factory(engine)
    game_id = await create_game(sessions, car_id=car_id, level=level, mode=GameMode.HUMAN)
    # LLM turns can take several seconds (tool calls included): the default timeout is too short.
    http = httpx.AsyncClient(timeout=60)
    client = await create_client(
        seller_url, client_config=ClientConfig(streaming=False, httpx_client=http)
    )
    print(f"\nGame {game_id} · level {int(level)} ({level.name}) · car {car_id}")
    print("Commands: /quit to walk away. Type your offer or questions.\n")
    try:
        while True:
            async with sessions() as s:
                status, turn, cap, floor, final, list_price = (
                    await s.execute(_STATE, {"g": game_id})
                ).one()
            if status != "open":
                break
            message = (await asyncio.to_thread(input, f"you [{turn}/{cap}]> ")).strip()
            if message == "/quit":
                break
            if not message:
                continue
            reply = await _ask(client, game_id, message)
            price = f" · price ${reply.price_usd:,}" if reply.price_usd else ""
            print(f"Sam> {reply.message}\n     [{reply.intent}{price}]\n")
        async with sessions() as s:
            status, turn, cap, floor, final, list_price = (
                await s.execute(_STATE, {"g": game_id})
            ).one()
        print(f"\nGame over: {status}. List ${list_price:,}, secret floor ${floor:,}.")
        if final:
            captured = (list_price - final) / (list_price - floor)
            print(f"You bought it for ${final:,}: {captured:.0%} of the possible discount.")
    finally:
        await client.close()
        await http.aclose()
        await engine.dispose()


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Haggle with the seller agent.")
    parser.add_argument("--car", default="dodge-challenger-rt-1970")
    parser.add_argument("--level", type=int, choices=[1, 2, 3], default=3)
    parser.add_argument("--url", default="http://127.0.0.1:8200")
    args = parser.parse_args()
    asyncio.run(play(args.car, Level(args.level), args.url))
