"""Find money amounts in free text: "$27,385", "27.385", "27 385", "27k", "27.4k", "27 grand".

Used by the seller's guards (is this offer really in the buyer's message? does the seller's
message mention a number near the floor?) and, from week 6, by the leak detector. Deliberately
conservative: it only reads digit-based forms. Spelled-out numbers ("twenty-seven thousand")
and encodings are the evals' job (docs/06-evaluation-plan.md §4.2).
"""

import re

# Thousands separators: comma, dot (European style), space and no-break space (written as an
# escape so the source contains no invisible characters).
_SEP = "[,. \u00a0]"

# 1) "$27,385" / "27.385" / "27 385" (thousands separators) or "27385"
# 2) optional decimals + k/grand suffix: "27k", "27.4k", "27 grand", "27K"
_AMOUNT = re.compile(
    r"(?<![\w.])\$?\s?"
    rf"(?P<num>\d{{1,3}}(?:{_SEP}\d{{3}})+|\d+(?:\.\d+)?)"
    r"\s?(?P<suffix>k|grand|thousand)?(?![\w])",
    re.IGNORECASE,
)

MIN_PRICE_LIKE = 1_000  # ignore small numbers (years are filtered by the caller's tolerance)


def extract_amounts(text: str) -> list[int]:
    """All amounts >= 1,000 found in `text`, as whole dollars, in order of appearance."""
    amounts: list[int] = []
    for match in _AMOUNT.finditer(text):
        raw, suffix = match["num"], (match["suffix"] or "").lower()
        if suffix:
            value = float(raw.replace(",", "")) * 1_000
        elif re.fullmatch(rf"\d{{1,3}}(?:{_SEP}\d{{3}})+", raw):
            value = float(re.sub(_SEP, "", raw))
        else:
            value = float(raw)
        if value >= MIN_PRICE_LIKE:
            amounts.append(round(value))
    return amounts


def mentions_amount(text: str, amount: int, tolerance_usd: int = 0) -> bool:
    return any(abs(found - amount) <= tolerance_usd for found in extract_amounts(text))
