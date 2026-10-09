"""Distributed tracing for the MCP server.

`TraceContextMiddleware` reads the caller's W3C `traceparent` header and makes it the current
OpenTelemetry context for the whole request. Every Langfuse observation the tools create then
becomes a child of the seller's tool span: one trace across both services.
"""

from starlette.types import ASGIApp, Receive, Scope, Send

from haggle_core.tracing import attached_trace_context


class TraceContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1"): v.decode("latin-1") for k, v in scope["headers"]}
        with attached_trace_context(headers):
            await self.app(scope, receive, send)
