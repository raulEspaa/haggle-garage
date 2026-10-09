"""RAG tests: sheet parsing and hygiene (pure), storage and search (Postgres, fake embedder),
and retrieval quality with real Gemini embeddings (marked `llm`, never in CI)."""

import os
import re
from pathlib import Path

import pytest
import yaml
from sqlalchemy import Engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from haggle_core.seed import load_seed
from haggle_mcp.rag.embeddings import FakeEmbedder, GeminiEmbedder
from haggle_mcp.rag.sheets import load_sheets, parse_sheet
from haggle_mcp.rag.store import SheetRetriever, ingest_sheets

REPO = Path(__file__).resolve().parents[3]
SHEETS_DIR = REPO / "db" / "sheets"
QUESTIONS = yaml.safe_load((REPO / "evals" / "datasets" / "rag_questions.yaml").read_text())

# Phrases that read like instructions to a model. Sheets are reference DATA that the seller's
# LLM reads: an instruction hidden in one would be an indirect prompt injection (threat T7).
INSTRUCTION_LIKE = re.compile(
    r"\b(ignore (all|previous|the above)|you must|you are an?|system prompt|as an ai|disregard)\b",
    re.IGNORECASE,
)


# ----------------------------------------------------------------------------- pure
def test_every_sheet_parses_with_sources_and_sections() -> None:
    sheets = load_sheets(SHEETS_DIR)

    assert len(sheets) == 3
    for sheet in sheets:
        assert sheet.meta.sources, sheet.meta.slug
        assert len(sheet.sections) >= 5, sheet.meta.slug


def test_every_car_in_the_seed_has_a_sheet(seed_file: Path) -> None:
    slugs = {s.meta.slug for s in load_sheets(SHEETS_DIR)}

    assert {car.id for car in load_seed(seed_file).cars} <= slugs


def test_sheets_contain_no_instruction_like_text() -> None:
    for sheet in load_sheets(SHEETS_DIR):
        for section in sheet.sections:
            assert not INSTRUCTION_LIKE.search(section.content), (sheet.meta.slug, section.title)


def test_template_is_not_ingested() -> None:
    assert "make-model-year" not in {s.meta.slug for s in load_sheets(SHEETS_DIR)}


def test_html_comments_are_stripped() -> None:
    sheet = parse_sheet(
        "---\nslug: a-b\nmake: A\nmodel: B\nyears: '1970'\ntitle: A B\nversion: 1\n"
        "sources: [https://example.org]\n---\n<!-- secret note -->\n## One\nText.\n"
    )

    assert "secret note" not in sheet.body_md
    assert [s.title for s in sheet.sections] == ["One"]


def test_sheet_without_front_matter_is_rejected() -> None:
    with pytest.raises(ValueError, match="front matter"):
        parse_sheet("## Just a section\nText")


# ----------------------------------------------------------------------------- database
@pytest.mark.db
async def test_ingest_stores_chunks_links_cars_and_is_idempotent(
    session_factory: async_sessionmaker[AsyncSession], migrated_engine: Engine
) -> None:
    sheets = load_sheets(SHEETS_DIR)

    first = await ingest_sheets(session_factory, sheets, FakeEmbedder())
    second = await ingest_sheets(session_factory, sheets, FakeEmbedder())

    with migrated_engine.connect() as conn:
        chunks = conn.scalar(text("SELECT count(*) FROM sheet_chunks"))
        unlinked = conn.scalar(text("SELECT count(*) FROM cars WHERE model_sheet_id IS NULL"))
    assert first == second == chunks
    assert unlinked == 0


@pytest.mark.db
async def test_search_ranks_the_matching_chunk_first(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await ingest_sheets(session_factory, load_sheets(SHEETS_DIR), FakeEmbedder())
    retriever = SheetRetriever(session_factory, FakeEmbedder())

    hits = await retriever.search("Six Pack carburetors rebuilt Plum Crazy", top_k=3)

    assert hits[0].sheet_slug == "dodge-challenger-rt-1970"
    assert hits[0].score >= hits[-1].score


# ----------------------------------------------------------------------------- real LLM
@pytest.mark.llm
@pytest.mark.db
async def test_retrieval_quality_with_gemini_embeddings(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """hit@3 >= 0.9 on the dealer-specific question set (docs/06-evaluation-plan.md §2.3)."""
    if not os.environ.get("GOOGLE_API_KEY"):
        pytest.skip("GOOGLE_API_KEY not set")
    embedder = GeminiEmbedder()
    await ingest_sheets(session_factory, load_sheets(SHEETS_DIR), embedder)
    retriever = SheetRetriever(session_factory, embedder)

    hits = 0
    for item in QUESTIONS["questions"]:
        results = await retriever.search(item["q"], top_k=3)
        hits += any(r.sheet_slug == item["sheet"] and r.section == item["section"] for r in results)

    assert hits / len(QUESTIONS["questions"]) >= 0.9
