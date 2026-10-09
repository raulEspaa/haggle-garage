"""Estimated cost of LLM calls (Gemini API paid tier, standard, USD per 1M tokens).

Source: https://ai.google.dev/gemini-api/docs/pricing (verified 2026-10-08, docs/10-sources.md).
Used by the daily soft budget (docs/07-threat-model.md §5). Development on the free tier still
records the *equivalent* paid cost, so budget logic is exercised before launch.
"""

from decimal import Decimal

PRICES_PER_MILLION: dict[str, tuple[Decimal, Decimal]] = {
    "gemini-3.1-flash-lite": (Decimal("0.25"), Decimal("1.50")),
    "gemini-3.5-flash-lite": (Decimal("0.30"), Decimal("2.50")),
    "gemini-3.8-flash": (Decimal("0.75"), Decimal("3.75")),  # until 2026-12-31, then doubles
    "gemini-embedding-2": (Decimal("0.20"), Decimal("0")),
}
UNKNOWN_MODEL_PRICE = (
    Decimal("2.00"),
    Decimal("12.00"),
)  # pessimistic: an unknown model costs a lot


def estimate_cost_usd(model_id: str, input_tokens: int, output_tokens: int) -> Decimal:
    price_in, price_out = PRICES_PER_MILLION.get(model_id, UNKNOWN_MODEL_PRICE)
    cost = (input_tokens * price_in + output_tokens * price_out) / Decimal(1_000_000)
    return cost.quantize(Decimal("0.000001"))
