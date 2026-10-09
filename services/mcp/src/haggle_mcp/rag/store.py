"""Persist sheets in Postgres and search them with pgvector.

Search uses cosine distance (`<=>` in pgvector) and the HNSW index from migration 0001.
Score returned to callers = 1 - distance, so 1.0 means identical direction.
"""

from dataclasses import dataclass

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from haggle_core.db.models import Car, ModelSheet, SheetChunk
from haggle_core.tracing import observation
from haggle_mcp.rag.embeddings import Embedder
from haggle_mcp.rag.sheets import Sheet


@dataclass(frozen=True, slots=True)
class SearchHit:
    sheet_slug: str
    section: str
    text: str
    score: float


async def ingest_sheets(
    sessions: async_sessionmaker[AsyncSession], sheets: list[Sheet], embedder: Embedder
) -> int:
    """Upsert sheets, replace their chunks, link cars whose id equals the sheet slug.

    Embeddings are computed BEFORE opening the transaction: never hold a DB transaction open
    while waiting on a network call. Returns the number of chunks stored.
    """
    vectors_per_sheet = [
        # Contextual chunk header: "<car> — <section>". Without the car name, a "Market notes"
        # chunk of one car looked like every other car's. Measured on 10 questions (2026-10-09):
        # hit@3 9/10 -> 10/10, top-1 result always the right car; section hit@1 6/10 -> 5/10.
        await embedder.embed_documents(
            [(f"{sheet.meta.title} — {s.title}", s.content) for s in sheet.sections]
        )
        for sheet in sheets
    ]
    total = 0
    async with sessions() as session, session.begin():
        for sheet, vectors in zip(sheets, vectors_per_sheet, strict=True):
            meta = sheet.meta
            stmt = insert(ModelSheet).values(
                slug=meta.slug,
                make=meta.make,
                model=meta.model,
                years=meta.years,
                title=meta.title,
                body_md=sheet.body_md,
                version=meta.version,
            )
            sheet_id = await session.scalar(
                stmt.on_conflict_do_update(
                    index_elements=[ModelSheet.slug],
                    set_={
                        k: stmt.excluded[k]
                        for k in ("make", "model", "years", "title", "body_md", "version")
                    },
                ).returning(ModelSheet.id)
            )
            await session.execute(delete(SheetChunk).where(SheetChunk.sheet_id == sheet_id))
            session.add_all(
                SheetChunk(
                    sheet_id=sheet_id,
                    chunk_index=section.index,
                    section=section.title,
                    content=section.content,
                    embedding=vector,
                    token_count=section.approx_tokens,
                )
                for section, vector in zip(sheet.sections, vectors, strict=True)
            )
            await session.execute(
                update(Car).where(Car.id == meta.slug).values(model_sheet_id=sheet_id)
            )
            total += len(sheet.sections)
    return total


class SheetRetriever:
    """Query side of RAG: embed the question, then nearest-neighbour search in pgvector."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], embedder: Embedder) -> None:
        self._sessions = sessions
        self._embedder = embedder

    async def search(self, query: str, top_k: int) -> list[SearchHit]:
        with observation("rag.search", "retriever", input={"query": query, "top_k": top_k}) as obs:
            with observation("rag.embed_query", "embedding", input=query):
                vector = await self._embedder.embed_query(query)
            hits = await search(self._sessions, vector, top_k)
            obs.update(
                output=[
                    {"sheet": h.sheet_slug, "section": h.section, "score": h.score} for h in hits
                ]
            )
            return hits


async def search(
    sessions: async_sessionmaker[AsyncSession], query_vector: list[float], top_k: int
) -> list[SearchHit]:
    distance = SheetChunk.embedding.cosine_distance(query_vector)
    async with sessions() as session:
        rows = await session.execute(
            select(
                ModelSheet.slug, SheetChunk.section, SheetChunk.content, distance.label("distance")
            )
            .join(ModelSheet, ModelSheet.id == SheetChunk.sheet_id)
            .order_by(distance)
            .limit(top_k)
        )
        return [
            SearchHit(sheet_slug=slug, section=section, text=content, score=round(1 - dist, 4))
            for slug, section, content, dist in rows
        ]
