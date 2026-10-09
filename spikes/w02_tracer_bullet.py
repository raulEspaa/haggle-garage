"""Week 2 tracer bullet: the thinnest path through ADK -> MCP -> A2A, with NO real LLM.

Questions it answers (docs/02-architecture.md §11):
  S1  ADK 2.x and the MCP Python SDK v2 coexist (answered by `uv lock`; this script imports both)
  S2  to_a2a() + DatabaseSessionService: does the A2A contextId become the ADK session id?
      Is a client-provided contextId accepted? Does state persist across two messages?
  S3  McpToolset(header_provider=...) receives the session, so code (not the LLM) can send
      X-Haggle-Game-Id to the MCP server.
  S6  Where does the agent's answer land in the A2A response (task artifact? status message?)

How the LLM is avoided: a `before_model_callback` that returns an LlmResponse skips the model
call entirely (documented ADK behaviour). The "script" asks for the tool once, then answers
with the tool's result. Zero tokens, fully deterministic.

Run (needs `make db-up` and a database named haggle_spike):
    uv run python spikes/w02_tracer_bullet.py
"""

import asyncio
import contextlib
import json
import uuid

import uvicorn
from a2a.client import ClientConfig, create_client
from a2a.helpers import get_artifact_text, get_message_text, new_text_message
from a2a.types import a2a_pb2
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.genai import types
from mcp.server import MCPServer
from mcp.server.mcpserver import Context

MCP_PORT, A2A_PORT = 8765, 8766
DB_URL = "postgresql+psycopg://haggle:haggle@localhost:5432/haggle_spike"

# ----------------------------------------------------------------------------- MCP server (v2)
mcp = MCPServer("spike-mcp")


@mcp.tool()
def whoami(note: str, ctx: Context) -> dict[str, str | None]:
    """Echo back the trusted game id header and the note the model sent."""
    headers = ctx.headers or {}
    return {"game_id_header": headers.get("x-haggle-game-id"), "note": note}


# ----------------------------------------------------------------------------- ADK agent
def scripted_model(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> LlmResponse | None:
    """Pretend to be the LLM: call `whoami` first, then report its result as text."""
    last = llm_request.contents[-1] if llm_request.contents else None
    tool_results = [p.function_response for p in (last.parts or [])] if last else []
    tool_results = [r for r in tool_results if r is not None]
    if tool_results:
        text = "TOOL RESULT: " + json.dumps(tool_results[-1].response, default=str)
        return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]))
    call = types.FunctionCall(name="whoami", args={"note": "hello from the scripted model"})
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(function_call=call)]))


def game_headers(ctx: ReadonlyContext) -> dict[str, str]:
    # S3: code, not the LLM, decides which game this call belongs to.
    return {"X-Haggle-Game-Id": ctx.session.id}


def count_turns(callback_context: CallbackContext) -> None:
    # S2 persistence check: session state survives between A2A messages.
    callback_context.state["turns"] = callback_context.state.get("turns", 0) + 1


agent = LlmAgent(
    name="spike_seller",
    model="gemini-3.1-flash-lite",  # never called: the callback short-circuits it
    instruction="Spike agent.",
    tools=[
        McpToolset(
            connection_params=StreamableHTTPConnectionParams(
                url=f"http://127.0.0.1:{MCP_PORT}/mcp"
            ),
            header_provider=game_headers,
        )
    ],
    before_agent_callback=count_turns,
    before_model_callback=scripted_model,
)
session_service = DatabaseSessionService(db_url=DB_URL)
runner = Runner(app_name="spike", agent=agent, session_service=session_service)
a2a_app = to_a2a(agent, host="127.0.0.1", port=A2A_PORT, runner=runner)


# ----------------------------------------------------------------------------- harness
async def serve(app: object, port: int) -> uvicorn.Server:
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    asyncio.get_running_loop().create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.05)
    return server


async def send(client: object, text: str, context_id: str) -> a2a_pb2.StreamResponse:
    message = new_text_message(text, context_id=context_id)
    last = None
    async for response in client.send_message(a2a_pb2.SendMessageRequest(message=message)):  # type: ignore[attr-defined]
        last = response
    assert last is not None
    return last


def describe(response: a2a_pb2.StreamResponse) -> str:
    kind = response.WhichOneof("payload")
    if kind == "task":
        task = response.task
        texts = [get_artifact_text(a) for a in task.artifacts]
        status_text = (
            get_message_text(task.status.message) if task.status.HasField("message") else ""
        )
        return (
            f"Task id={task.id} context={task.context_id} "
            f"state={a2a_pb2.TaskState.Name(task.status.state)} "
            f"artifacts={texts} status_message={status_text!r}"
        )
    if kind == "message":
        return f"Message context={response.message.context_id} text={get_message_text(response.message)!r}"
    return f"{kind}: {response}"


async def main() -> None:
    mcp_server = await serve(
        mcp.streamable_http_app(stateless_http=True, json_response=True), MCP_PORT
    )
    a2a_server = await serve(a2a_app, A2A_PORT)
    try:
        client = await create_client(
            f"http://127.0.0.1:{A2A_PORT}", client_config=ClientConfig(streaming=False)
        )
        game_id = str(uuid.uuid4())  # S2: client-provided contextId (our game id)
        print(f"client contextId = {game_id}")
        for text in ("I offer 27000", "OK, 31500 then"):
            print("->", describe(await send(client, text, game_id)))

        sessions = await session_service.list_sessions(app_name="spike", user_id=None)
        for s in sessions.sessions:
            full = await session_service.get_session(
                app_name="spike", user_id=s.user_id, session_id=s.id
            )
            print(
                f"session id={s.id} user={s.user_id} state={full.state if full else None} "
                f"events={len(full.events) if full else 0}"
            )
    finally:
        a2a_server.should_exit = True
        mcp_server.should_exit = True
        await asyncio.sleep(0.3)
        with contextlib.suppress(Exception):
            await client.close()  # type: ignore[possibly-undefined]


if __name__ == "__main__":
    asyncio.run(main())
