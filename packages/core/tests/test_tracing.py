"""Distributed-tracing helpers: the trace context must survive a trip through HTTP headers."""

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from haggle_core.tracing import attached_trace_context, inject_trace_headers, observation


def test_trace_context_round_trips_through_headers() -> None:
    tracer = TracerProvider().get_tracer("test")
    with tracer.start_as_current_span("seller.tool_call") as caller:
        headers = inject_trace_headers({"X-Haggle-Token": "t"})

    assert headers["traceparent"].startswith("00-")  # W3C Trace Context, version 00
    with attached_trace_context(headers):  # what the MCP middleware does
        remote = trace.get_current_span().get_span_context()
    assert remote.trace_id == caller.get_span_context().trace_id
    assert remote.span_id == caller.get_span_context().span_id  # MCP steps become its children


def test_context_is_detached_after_the_request() -> None:
    tracer = TracerProvider().get_tracer("test")
    with tracer.start_as_current_span("caller"):
        headers = inject_trace_headers({})

    with attached_trace_context(headers):
        pass

    assert not trace.get_current_span().get_span_context().is_valid


def test_observation_is_a_no_op_without_langfuse_keys() -> None:
    with observation("policy.decide", "evaluator", input={"offer_usd": 1}) as obs:
        obs.update(output={"decision": "counter"})  # must not raise


def _finished_span(scope: str, name: str, attributes: dict[str, str]) -> object:
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    with provider.get_tracer(scope).start_as_current_span(name, attributes=attributes):
        pass
    return exporter.get_finished_spans()[0]


def test_mcp_tool_calls_are_exported_but_the_handshake_is_not() -> None:
    from haggle_core.tracing import should_export_span

    call = _finished_span(
        "mcp-python-sdk", "MCP send tools/call x", {"mcp.method.name": "tools/call"}
    )
    handshake = _finished_span(
        "mcp-python-sdk", "MCP send initialize", {"mcp.method.name": "initialize"}
    )
    generic = _finished_span("some.http.lib", "GET /", {})

    assert should_export_span(call)
    assert not should_export_span(handshake)
    assert not should_export_span(generic)  # Langfuse's default filter still applies
