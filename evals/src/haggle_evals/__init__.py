"""Haggle Garage evaluation suite (docs/06-evaluation-plan.md). Built in week 6."""

import os

# Same reason as in haggle_buyer: a2a-sdk's own spans break the trace tree in Langfuse.
os.environ.setdefault("OTEL_INSTRUMENTATION_A2A_SDK_ENABLED", "false")
