"""Haggle Garage shared core: settings, domain enums and database models.

Rule: nothing in this package may import an agent framework (ADK, LangGraph, MCP server SDK).
Every service depends on core, so a heavy import here would bloat every image.
"""
