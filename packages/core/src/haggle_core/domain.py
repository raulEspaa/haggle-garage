"""Domain vocabulary shared by every service.

These enums are the single source of truth for allowed values.
The database enforces the same values through CHECK constraints built from them (see db/models.py).
"""

from enum import IntEnum, StrEnum


class Level(IntEnum):
    NAIVE = 1  # floor in the prompt, no defenses
    HARDENED = 2  # floor in the prompt + defensive prompt + output filter
    BLIND = 3  # the model never sees the floor; code decides prices


class GameMode(StrEnum):
    HUMAN = "human"
    AGENT = "agent"
    EVAL = "eval"


class GameStatus(StrEnum):
    OPEN = "open"
    DEAL = "deal"
    WALKED_AWAY = "walked_away"
    TURN_LIMIT = "turn_limit"
    FLOOR_CLAIMED = "floor_claimed"
    EXPIRED = "expired"


class TurnRole(StrEnum):
    BUYER = "buyer"
    SELLER = "seller"


class EventKind(StrEnum):
    OFFER_EVALUATED = "offer_evaluated"
    CLOSE_ATTEMPT = "close_attempt"


class Decision(StrEnum):
    ACCEPT = "accept"
    COUNTER = "counter"
    REJECT = "reject"


class CloseOutcome(StrEnum):
    CLOSED = "closed"
    REJECTED = "rejected"


class McpBackend(StrEnum):
    HOME = "home"
    CLOUD = "cloud"


class LlmComponent(StrEnum):
    SELLER = "seller"
    BUYER = "buyer"
    JUDGE = "judge"
    EMBEDDER = "embedder"
