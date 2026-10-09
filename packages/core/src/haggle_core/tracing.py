"""Tracing helpers shared by every service: Langfuse over OpenTelemetry.

Three jobs:
* `setup_langfuse()` turns tracing on when LANGFUSE_* keys exist (otherwise everything here is a
  cheap no-op: tests and CI run untraced).
* `observation()` records a typed step (tool, retriever, guardrail...). Typed observations are
  what Langfuse's Agent Graph draws as nodes.
* Distributed tracing: the caller `inject_trace_headers()` into an HTTP request and the callee
  `attached_trace_context()` from the request headers, so ONE trace spans several services.

Langfuse's default span filter drops generic OTel spans (ASGI, SQLAlchemy...): only spans from
the Langfuse SDK, with gen_ai.* attributes, or from known LLM instrumentors are exported. That is
why services create Langfuse observations instead of relying on generic instrumentation.
"""

import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any, Literal

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.propagate import extract, inject

ObservationType = Literal[
    "span", "tool", "chain", "retriever", "embedding", "guardrail", "evaluator", "agent"
]

_enabled = False

# The MCP Python SDK v2 traces every JSON-RPC call itself (tracer "mcp-python-sdk") and propagates
# the context in the request `_meta`. Langfuse's default filter drops the CLIENT-side span (no
# gen_ai.* attributes), which broke the chain seller tool -> MCP server into a detached branch.
# Only `tools/call` spans are kept: the handshake (initialize, tools/list) is noise in the graph.
MCP_SDK_SCOPE = "mcp-python-sdk"


def should_export_span(span: Any) -> bool:
    """Langfuse's default filter + the MCP SDK's tools/call spans (client and server side)."""
    from langfuse.span_filter import is_default_export_span

    if is_default_export_span(span):
        return True
    scope = getattr(span, "instrumentation_scope", None)
    attributes = getattr(span, "attributes", None) or {}
    return (
        scope is not None
        and scope.name == MCP_SDK_SCOPE
        and attributes.get("mcp.method.name") == "tools/call"
    )


def setup_langfuse() -> bool:
    """Initialise the Langfuse exporter if keys are configured. Safe to call more than once."""
    global _enabled
    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
        return False
    from langfuse import Langfuse

    Langfuse(should_export_span=should_export_span)  # becomes the client get_client() returns
    _enabled = True
    return True


class _NoOpObservation:
    def update(self, **_: Any) -> None:
        """Accept and ignore updates when tracing is off."""


@contextmanager
def observation(
    name: str, as_type: ObservationType, input: Any = None, metadata: Any = None
) -> Iterator[Any]:
    """Typed step in the current trace. NEVER put secrets (the floor!) in input/output/metadata:
    trace storage is one more place a secret could leak from."""
    if not _enabled:
        yield _NoOpObservation()
        return
    from langfuse import get_client

    with get_client().start_as_current_observation(
        name=name, as_type=as_type, input=input, metadata=metadata
    ) as obs:
        yield obs


def tag_current_trace(tags: list[str], metadata: Mapping[str, str]) -> None:
    """Attach filterable tags and metadata to the whole trace (Langfuse `langfuse.trace.*`
    OpenTelemetry attribute convention). Works from any span inside the trace."""
    span = trace.get_current_span()
    if not span.is_recording():
        return
    span.set_attribute("langfuse.trace.tags", tags)
    for key, value in metadata.items():
        span.set_attribute(f"langfuse.trace.metadata.{key}", value)


def inject_trace_headers(headers: dict[str, str]) -> dict[str, str]:
    """Add the W3C `traceparent` (and `tracestate`) of the current span to outgoing headers."""
    inject(headers)
    return headers


@contextmanager
def attached_trace_context(headers: Mapping[str, str]) -> Iterator[None]:
    """Make the caller's trace (from incoming `traceparent`) the current context."""
    token = otel_context.attach(extract(dict(headers)))
    try:
        yield
    finally:
        otel_context.detach(token)
