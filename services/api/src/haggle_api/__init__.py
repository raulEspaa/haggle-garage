"""Haggle Garage public API (FastAPI)."""

import os

# The a2a-sdk wraps every A2A call in its own OpenTelemetry spans. Langfuse's export filter drops
# them, so the seller's spans hung off a parent nobody received and the buyer -> seller trace
# broke in two. Turned off here, in the package __init__, because a2a-sdk reads the variable
# once at import time, before any submodule of this package imports it.
os.environ.setdefault("OTEL_INSTRUMENTATION_A2A_SDK_ENABLED", "false")
