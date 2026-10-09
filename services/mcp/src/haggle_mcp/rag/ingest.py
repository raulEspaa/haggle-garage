"""CLI: embed db/sheets/*.md with Gemini and store them in Postgres.

    uv run haggle-ingest                 # HAGGLE_DATABASE_URL + Gemini backend vars from .env
    uv run haggle-ingest --dir db/sheets

Idempotent: re-running replaces the chunks of each sheet (cost: a few thousand tokens).
"""

import argparse
import asyncio
from pathlib import Path

from dotenv import load_dotenv

from haggle_core.db.session import create_engine, create_session_factory
from haggle_mcp.rag.embeddings import GeminiEmbedder
from haggle_mcp.rag.sheets import load_sheets
from haggle_mcp.rag.store import ingest_sheets


async def _run(directory: Path) -> None:
    sheets = load_sheets(directory)
    engine = create_engine()
    try:
        chunks = await ingest_sheets(create_session_factory(engine), sheets, GeminiEmbedder())
    finally:
        await engine.dispose()
    print(f"Ingested {len(sheets)} sheets, {chunks} chunks from {directory}")


def main(argv: list[str] | None = None) -> None:
    load_dotenv()  # the Gemini backend vars are read by the google-genai client, not our settings
    parser = argparse.ArgumentParser(description="Embed model sheets into pgvector.")
    parser.add_argument("--dir", type=Path, default=Path("db/sheets"))
    asyncio.run(_run(parser.parse_args(argv).dir))
