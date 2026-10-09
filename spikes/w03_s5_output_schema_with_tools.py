"""Spike S5 (week 3): does output_schema work together with tools on gemini-3.1-flash-lite?

The seller must (1) call a tool to get a code-decided price and (2) answer with a structured
SellerTurn that code can validate. Uses the real Gemini API: a few hundred tokens.

    uv run python spikes/w03_s5_output_schema_with_tools.py
"""

import asyncio
from typing import Literal

from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel


class SellerTurn(BaseModel):
    message: str
    intent: Literal["counter", "accept", "reject", "inform"]
    price_usd: int | None


CALLS: list[int] = []


def evaluate_offer(offer_usd: int) -> dict[str, object]:
    """Evaluate the buyer's offer. Returns the only price you may quote."""
    CALLS.append(offer_usd)
    return {"decision": "counter", "counter_usd": 98_400}


async def main() -> None:
    load_dotenv(".env")
    agent = LlmAgent(
        name="s5_seller",
        model="gemini-3.1-flash-lite",
        instruction="You sell a 1970 Dodge Challenger R/T. For any price offer, call evaluate_offer "
        "and quote only the price it returns.",
        tools=[evaluate_offer],
        output_schema=SellerTurn,
    )
    runner = InMemoryRunner(agent=agent, app_name="s5")
    session = await runner.session_service.create_session(app_name="s5", user_id="u")
    final = None
    async for event in runner.run_async(
        user_id="u",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text="I offer 80,000 dollars.")]),
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final = "".join(p.text or "" for p in event.content.parts)
    print("tool calls:", CALLS)
    print("final raw:", final)
    print("parsed:", SellerTurn.model_validate_json(final or "{}"))


asyncio.run(main())
