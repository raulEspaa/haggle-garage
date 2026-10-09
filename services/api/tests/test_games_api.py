"""The public API end to end: real Postgres, real HTTP stack, FAKE seller (no LLM, no network).

The fake does what the real seller does to the database on each message (reserve the turn,
write the turn pair, close the deal on `close`), so the api sees a realistic game.
"""

import itertools
import uuid
from collections.abc import Callable, Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, insert, select, text, update

from haggle_api.main import create_app
from haggle_api.settings import ApiSettings
from haggle_core.a2a_client import SellerUnavailableError
from haggle_core.contracts import SellerIntent, SellerTurn
from haggle_core.db.models import Game, Turn
from haggle_core.domain import GameStatus, TurnRole

pytestmark = pytest.mark.db

CAR = "dodge-challenger-rt-1970"
_ips = (f"203.0.113.{n % 250}, 10.0.0.{n // 250}" for n in itertools.count(1))


class FakeSeller:
    """Stands in for A2ASellerClient. `script` decides each reply; `error` simulates an outage."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.calls: list[tuple[uuid.UUID, str]] = []
        self.script: Callable[[str], SellerTurn] = lambda _: SellerTurn(
            message="I can do $36,500.", intent=SellerIntent.COUNTER, price_usd=36_500
        )
        self.error: SellerUnavailableError | None = None

    async def send(self, game_id: uuid.UUID, text: str) -> SellerTurn:
        self.calls.append((game_id, text))
        if self.error:
            raise self.error
        reply = self.script(text)
        with self.engine.begin() as conn:
            turn = conn.scalar(
                update(Game)
                .where(Game.id == game_id)
                .values(turn_count=Game.turn_count + 1, last_activity_at=func.now())
                .returning(Game.turn_count)
            )
            assert turn is not None
            conn.execute(
                insert(Turn),
                [
                    {
                        "game_id": game_id,
                        "seq": 2 * turn - 1,
                        "role": TurnRole.BUYER,
                        "content": text,
                    },
                    {
                        "game_id": game_id,
                        "seq": 2 * turn,
                        "role": TurnRole.SELLER,
                        "content": reply.message,
                        "seller_turn": reply.model_dump(mode="json"),
                    },
                ],
            )
            if reply.intent is SellerIntent.CLOSE:
                conn.execute(
                    update(Game)
                    .where(Game.id == game_id)
                    .values(status=GameStatus.DEAL, final_price_usd=reply.price_usd)
                )
        return reply

    async def aclose(self) -> None:
        pass


def generous(**overrides: Any) -> ApiSettings:
    """Limits high enough that earlier tests never throttle later ones."""
    values: dict[str, Any] = {
        "trusted_proxy_hops": 2,  # each test gets its own client IP through X-Forwarded-For
        "games_per_ip_per_day": 5,
        "games_per_hour_global": 10_000,
        "messages_per_ip_per_hour": 30,
        "daily_budget_usd": Decimal("1000"),
    }
    return ApiSettings(**(values | overrides))


@pytest.fixture
def seller(migrated_engine: Engine) -> FakeSeller:
    return FakeSeller(migrated_engine)


MakeClient = Callable[..., TestClient]


@pytest.fixture
def make_client(database_url: str, seller: FakeSeller) -> Iterator[MakeClient]:
    clients: list[TestClient] = []

    def _make(**overrides: Any) -> TestClient:
        app = create_app(generous(**overrides), seller=seller, database_url=database_url)
        client = TestClient(app, headers={"X-Forwarded-For": next(_ips)})
        client.__enter__()  # runs the lifespan (engine + GameService)
        clients.append(client)
        return client

    yield _make
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def client(make_client: MakeClient) -> TestClient:
    return make_client()


def start(client: TestClient, level: int = 3) -> tuple[str, dict[str, str]]:
    response = client.post("/api/games", json={"car_id": CAR, "level": level})
    assert response.status_code == 201, response.text
    body = response.json()
    return body["game_id"], {"X-Game-Token": body["game_token"]}


def floor_of(engine: Engine, game_id: str) -> int:
    with engine.connect() as conn:
        floor: int = conn.scalar(select(Game.floor_usd).where(Game.id == uuid.UUID(game_id)))
    return floor


# ----------------------------------------------------------------------------- catalog and pages
def test_catalog_lists_the_seeded_cars_and_levels(client: TestClient) -> None:
    cars = client.get("/api/cars").json()
    levels = client.get("/api/levels").json()

    assert {c["id"] for c in cars} >= {CAR}
    assert "floor_usd" not in cars[0]
    assert [lvl["level"] for lvl in levels] == [1, 2, 3]


def test_unknown_car_is_a_problem_json_404(client: TestClient) -> None:
    response = client.get("/api/cars/ford-model-t-1908")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["title"] == "Unknown car"


def test_home_page_renders_cars_with_security_headers(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "1970 Dodge Challenger" in response.text
    assert "script-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-frame-options"] == "DENY"
    assert client.get("/about").status_code == 200


# ----------------------------------------------------------------------------- create
def test_create_returns_a_token_and_a_templated_greeting_without_calling_the_seller(
    client: TestClient, seller: FakeSeller, migrated_engine: Engine
) -> None:
    response = client.post("/api/games", json={"car_id": CAR, "level": 2})

    body = response.json()
    assert response.status_code == 201
    assert len(body["game_token"]) >= 40
    assert "1970 Dodge Challenger R/T" in body["seller_message"]
    assert f"${body['car']['list_price_usd']:,}" in body["seller_message"]
    assert "floor_usd" not in body
    assert seller.calls == []
    with migrated_engine.connect() as conn:
        stored = conn.execute(
            select(Game.game_token_hash, Game.client_ip_hash, Game.mode).where(
                Game.id == uuid.UUID(body["game_id"])
            )
        ).one()
    assert stored.game_token_hash != body["game_token"]  # only the hash is stored
    assert len(stored.client_ip_hash) == 64  # a daily HMAC, not the address
    assert "203.0.113" not in stored.client_ip_hash
    assert stored.mode == "human"


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"car_id": CAR, "level": 4}, "level"),
        ({"car_id": "../etc/passwd", "level": 1}, "car_id"),
        ({"car_id": CAR, "level": 1, "floor_usd": 1}, "floor_usd"),
    ],
)
def test_create_rejects_bad_input(client: TestClient, payload: dict[str, Any], field: str) -> None:
    response = client.post("/api/games", json=payload)

    assert response.status_code == 422
    assert field in response.json()["detail"]


def test_sixth_game_from_the_same_ip_in_a_day_is_429(client: TestClient) -> None:
    for _ in range(5):
        start(client)

    response = client.post("/api/games", json={"car_id": CAR, "level": 1})

    assert response.status_code == 429
    assert response.headers["retry-after"] == "3600"


def test_global_hourly_limit_is_429(make_client: MakeClient) -> None:
    response = make_client(games_per_hour_global=0).post(
        "/api/games", json={"car_id": CAR, "level": 1}
    )

    assert response.status_code == 429


def test_kill_switch_closes_the_demo(make_client: MakeClient) -> None:
    response = make_client(demo_enabled=False).post("/api/games", json={"car_id": CAR, "level": 1})

    assert response.status_code == 503


def test_spent_budget_closes_the_demo(make_client: MakeClient) -> None:
    response = make_client(daily_budget_usd=Decimal("0")).post(
        "/api/games", json={"car_id": CAR, "level": 1}
    )

    assert response.status_code == 503
    assert response.json()["title"] == "The dealership is closed for today"


# ----------------------------------------------------------------------------- messages
def test_message_is_forwarded_and_the_offer_is_shown(
    client: TestClient, seller: FakeSeller
) -> None:
    game_id, token = start(client)

    response = client.post(
        f"/api/games/{game_id}/messages", json={"text": "  30k?  "}, headers=token
    )

    body = response.json()
    assert response.status_code == 200, response.text
    assert seller.calls == [(uuid.UUID(game_id), "30k?")]  # cleaned before it leaves
    assert body["turn"] == 1
    assert body["turns_left"] == 11
    assert body["intent"] == "counter"
    assert body["offer_on_table_usd"] == 36_500
    assert body["status"] == "open"
    assert body["floor_usd"] is None  # never while the game is open


def test_closing_a_deal_reveals_the_floor_and_the_score(
    client: TestClient, seller: FakeSeller, migrated_engine: Engine
) -> None:
    game_id, token = start(client)
    seller.script = lambda _: SellerTurn(
        message="Deal!", intent=SellerIntent.CLOSE, price_usd=90_000
    )

    body = client.post(f"/api/games/{game_id}/messages", json={"text": "90k"}, headers=token).json()

    floor = floor_of(migrated_engine, game_id)
    list_price = client.get(f"/api/cars/{CAR}").json()["list_price_usd"]
    assert body["status"] == "deal"
    assert body["floor_usd"] == floor
    assert body["deal"]["price_usd"] == 90_000
    assert body["deal"]["discount_captured"] == round(
        (list_price - 90_000) / (list_price - floor), 3
    )


def test_messages_need_the_right_token(client: TestClient, seller: FakeSeller) -> None:
    game_id, _ = start(client)
    url = f"/api/games/{game_id}/messages"

    assert client.post(url, json={"text": "hi"}).status_code == 401
    assert (
        client.post(url, json={"text": "hi"}, headers={"X-Game-Token": "x" * 43}).status_code == 401
    )
    assert (
        client.post(f"/api/games/{uuid.uuid4()}/messages", json={"text": "hi"}).status_code == 404
    )
    assert seller.calls == []


@pytest.mark.parametrize(
    "text",
    ["", "   ", "a" * 501, "ignore\u200b previous", "bell\x07", "rtl\u202eoverride"],
)
def test_bad_messages_are_422_and_never_reach_the_seller(
    client: TestClient, seller: FakeSeller, text: str
) -> None:
    game_id, token = start(client)

    response = client.post(f"/api/games/{game_id}/messages", json={"text": text}, headers=token)

    assert response.status_code == 422
    assert seller.calls == []


def test_messages_after_the_game_ended_are_409(client: TestClient) -> None:
    game_id, token = start(client)
    client.post(f"/api/games/{game_id}/end", headers=token)

    response = client.post(f"/api/games/{game_id}/messages", json={"text": "hi"}, headers=token)

    assert response.status_code == 409


def test_a_second_message_while_one_is_in_flight_is_409(
    client: TestClient, seller: FakeSeller, migrated_engine: Engine
) -> None:
    game_id, token = start(client)
    key = int.from_bytes(uuid.UUID(game_id).bytes[:8], "big", signed=True)

    with migrated_engine.connect() as other_instance:  # e.g. a second Cloud Run container
        assert other_instance.scalar(select(func.pg_try_advisory_lock(key)))
        response = client.post(f"/api/games/{game_id}/messages", json={"text": "hi"}, headers=token)
        other_instance.execute(select(func.pg_advisory_unlock(key)))

    assert response.status_code == 409
    assert seller.calls == []


def test_hourly_message_limit_is_429(make_client: MakeClient) -> None:
    client = make_client(messages_per_ip_per_hour=2)
    game_id, token = start(client)
    url = f"/api/games/{game_id}/messages"

    statuses = [client.post(url, json={"text": "hi"}, headers=token).status_code for _ in range(3)]

    assert statuses == [200, 200, 429]


@pytest.mark.parametrize(("error", "status"), [("ReadTimeout", 504), ("ConnectError", 502)])
def test_seller_outage_maps_to_gateway_errors(
    client: TestClient, seller: FakeSeller, error: str, status: int
) -> None:
    game_id, token = start(client)
    seller.error = SellerUnavailableError(error)

    response = client.post(f"/api/games/{game_id}/messages", json={"text": "hi"}, headers=token)

    assert response.status_code == status
    assert response.json()["title"] == "The dealer is not answering"


def test_idle_game_expires_and_stays_expired(client: TestClient, migrated_engine: Engine) -> None:
    game_id, token = start(client)
    with migrated_engine.begin() as conn:
        conn.execute(
            text("UPDATE games SET last_activity_at = now() - interval '2 hours' WHERE id = :g"),
            {"g": game_id},
        )

    response = client.post(f"/api/games/{game_id}/messages", json={"text": "hi"}, headers=token)
    state = client.get(f"/api/games/{game_id}", headers=token).json()

    assert response.status_code == 409
    assert state["status"] == "expired"
    assert state["floor_usd"] == floor_of(migrated_engine, game_id)


# ----------------------------------------------------------------------------- state, guess, end
def test_state_returns_the_transcript_without_the_floor(client: TestClient) -> None:
    game_id, token = start(client)
    client.post(f"/api/games/{game_id}/messages", json={"text": "hello"}, headers=token)

    state = client.get(f"/api/games/{game_id}", headers=token).json()

    assert [line["role"] for line in state["transcript"]] == ["seller", "buyer", "seller"]
    assert state["floor_usd"] is None
    assert client.get(f"/api/games/{game_id}").status_code == 401


@pytest.mark.parametrize(("offset", "correct"), [(0.0, True), (0.014, True), (0.02, False)])
def test_floor_guess_within_tolerance(
    client: TestClient, migrated_engine: Engine, offset: float, correct: bool
) -> None:
    game_id, token = start(client)
    floor = floor_of(migrated_engine, game_id)
    guess = round(floor * (1 + offset))

    body = client.post(
        f"/api/games/{game_id}/floor-guess", json={"amount_usd": guess}, headers=token
    ).json()

    assert body["correct"] is correct
    assert body["floor_usd"] == floor
    assert body["status"] == "floor_claimed"


def test_only_one_floor_guess_per_game(client: TestClient) -> None:
    game_id, token = start(client)
    url = f"/api/games/{game_id}/floor-guess"
    client.post(url, json={"amount_usd": 30_000}, headers=token)

    assert client.post(url, json={"amount_usd": 31_000}, headers=token).status_code == 409


def test_walking_away_reveals_the_floor(client: TestClient, migrated_engine: Engine) -> None:
    game_id, token = start(client)

    state = client.post(f"/api/games/{game_id}/end", headers=token).json()

    assert state["status"] == "walked_away"
    assert state["floor_usd"] == floor_of(migrated_engine, game_id)
