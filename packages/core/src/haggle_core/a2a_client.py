"""Client side of A2A: send one buyer message to the seller, get a validated SellerTurn back.

Used by the api (human players), the buyer agent (week 5) and the evals. The experimental /
protobuf details of a2a-sdk 1.x stay behind this module (ADR-0006).

Retries: ONLY when the connection could not be established. A timeout or a 5xx after the request
was sent is NOT retried, because sending a message is not idempotent: the seller may already
have consumed a turn and called the LLM. Retrying would burn a second turn (and money).
"""

import uuid
from collections.abc import Awaitable, Callable
from typing import Protocol

import httpx
from a2a.client import Client, ClientConfig, create_client
from a2a.helpers import get_artifact_text, new_text_message
from a2a.types import a2a_pb2
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from haggle_core.contracts import SellerTurn

HeadersProvider = Callable[[], Awaitable[dict[str, str]]]


class SellerUnavailableError(Exception):
    """The seller could not be reached or did not answer properly."""


class SellerClient(Protocol):
    async def send(self, game_id: uuid.UUID, text: str) -> SellerTurn: ...

    async def aclose(self) -> None: ...


class A2ASellerClient:
    def __init__(
        self,
        base_url: str,
        timeout_s: float = 60.0,
        headers_provider: HeadersProvider | None = None,
    ) -> None:
        async def add_headers(request: httpx.Request) -> None:
            # Week 7: a Google ID token for Cloud Run IAM goes here (service-to-service auth).
            if headers_provider is not None:
                request.headers.update(await headers_provider())

        self._base_url = base_url
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s, connect=5.0), event_hooks={"request": [add_headers]}
        )
        self._client: Client | None = None

    @retry(
        retry=retry_if_exception_type(httpx.ConnectError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.2, max=2),
        reraise=True,
    )
    async def _connect(self) -> Client:
        """Fetch the agent card once and build the client (safe to retry: a GET)."""
        if self._client is None:
            self._client = await create_client(
                self._base_url,
                client_config=ClientConfig(streaming=False, httpx_client=self._http),
            )
        return self._client

    async def send(self, game_id: uuid.UUID, text: str) -> SellerTurn:
        try:
            client = await self._connect()
            request = a2a_pb2.SendMessageRequest(
                message=new_text_message(text, context_id=str(game_id))
            )
            last = None
            async for response in client.send_message(request):
                last = response
        except Exception as exc:  # network, timeout, protocol: the caller maps it to 502/504
            raise SellerUnavailableError(type(exc).__name__) from exc

        task = last.task if last is not None and last.HasField("task") else None
        if task is None or not task.artifacts:
            raise SellerUnavailableError("no answer in the A2A task")
        return SellerTurn.model_validate_json(get_artifact_text(task.artifacts[-1]))

    async def aclose(self) -> None:
        await self._http.aclose()
