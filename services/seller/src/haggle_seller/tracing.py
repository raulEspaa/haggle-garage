"""Langfuse tracing for ADK through OpenTelemetry (ADR-0004).

OpenInference's ADK instrumentor turns every agent run, LLM call and tool call into OTel spans;
the Langfuse client registers an exporter that ships them to Langfuse Cloud. Tracing is optional:
without keys the seller runs exactly the same, just untraced.
"""

import logging
import os

log = logging.getLogger(__name__)


def setup_tracing() -> bool:
    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
        log.info("Langfuse keys not set: tracing disabled")
        return False
    from openinference.instrumentation.google_adk import GoogleADKInstrumentor

    from haggle_core.tracing import setup_langfuse

    setup_langfuse()  # exporter from LANGFUSE_* env vars + enables our typed observations
    GoogleADKInstrumentor().instrument()
    log.info("Langfuse tracing enabled")
    return True
