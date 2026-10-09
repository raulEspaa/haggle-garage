"""HTTP routes: thin adapters from HTTP to GameService (≈ ASP.NET controllers)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from haggle_api.games import LEVELS, GameService
from haggle_api.schemas import (
    CarOut,
    FloorGuessIn,
    FloorGuessOut,
    GameStateOut,
    LevelOut,
    MessageIn,
    MessageOut,
    NewGameIn,
    NewGameOut,
)
from haggle_api.security import client_ip, ip_hash
from haggle_api.settings import ApiSettings

GameToken = Annotated[str | None, Header(alias="X-Game-Token")]


def get_service(request: Request) -> GameService:
    service: GameService = request.app.state.games
    return service


def get_settings(request: Request) -> ApiSettings:
    settings: ApiSettings = request.app.state.settings
    return settings


def get_ip_hash(request: Request, settings: Annotated[ApiSettings, Depends(get_settings)]) -> str:
    ip = client_ip(
        request.headers.get("x-forwarded-for"),
        request.client.host if request.client else None,
        settings.trusted_proxy_hops,
    )
    return ip_hash(ip, settings.ip_hash_secret.get_secret_value())


Service = Annotated[GameService, Depends(get_service)]
IpHash = Annotated[str, Depends(get_ip_hash)]

api = APIRouter(prefix="/api", tags=["game"])


@api.get("/levels")
async def levels() -> list[LevelOut]:
    return LEVELS


@api.get("/cars")
async def cars(service: Service) -> list[CarOut]:
    return await service.list_cars()


@api.get("/cars/{car_id}")
async def car(car_id: str, service: Service) -> CarOut:
    return await service.get_car(car_id)


@api.post("/games", status_code=status.HTTP_201_CREATED)
async def new_game(body: NewGameIn, service: Service, ip: IpHash) -> NewGameOut:
    return await service.create(body.car_id, body.level, ip)


@api.get("/games/{game_id}")
async def game_state(game_id: uuid.UUID, service: Service, token: GameToken = None) -> GameStateOut:
    return await service.state(game_id, token)


@api.post("/games/{game_id}/messages")
async def send_message(
    game_id: uuid.UUID, body: MessageIn, service: Service, ip: IpHash, token: GameToken = None
) -> MessageOut:
    return await service.send_message(game_id, token, body.text, ip)


@api.post("/games/{game_id}/floor-guess")
async def floor_guess(
    game_id: uuid.UUID, body: FloorGuessIn, service: Service, token: GameToken = None
) -> FloorGuessOut:
    return await service.guess_floor(game_id, token, body.amount_usd)


@api.post("/games/{game_id}/end")
async def end_game(game_id: uuid.UUID, service: Service, token: GameToken = None) -> GameStateOut:
    return await service.end(game_id, token)


def page_router(templates: Jinja2Templates) -> APIRouter:
    pages = APIRouter(include_in_schema=False)

    @pages.get("/", response_class=HTMLResponse)
    async def index(request: Request, service: Service) -> HTMLResponse:
        return templates.TemplateResponse(
            request, "index.html", {"cars": await service.list_cars(), "levels": LEVELS}
        )

    @pages.get("/about", response_class=HTMLResponse)
    async def about(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "about.html", {})

    return pages
