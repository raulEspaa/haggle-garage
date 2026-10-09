"""Embedding providers behind one small interface (≈ an `IEmbedder` in C#).

`typing.Protocol` is structural typing: any class with these two methods IS an Embedder, no
inheritance needed. Production uses Gemini; tests use a deterministic fake (no network, no cost).
"""

import asyncio
import hashlib
import math
import re
from typing import Protocol

from google import genai
from google.genai import types

from haggle_core.db.models import EMBEDDING_DIMS

GEMINI_EMBEDDING_MODEL = "gemini-embedding-2"


class Embedder(Protocol):
    async def embed_documents(self, documents: list[tuple[str, str]]) -> list[list[float]]:
        """Embed (title, text) pairs for storage."""
        ...

    async def embed_query(self, query: str) -> list[float]:
        """Embed a search query."""
        ...


class GeminiEmbedder:
    """gemini-embedding-2 at 768 dims (auto-renormalized, docs/10-sources.md).

    This model takes the task as an instruction inside the text instead of a task_type
    parameter: documents are formatted "title: ... | text: ...", queries
    "task: search result | query: ...". Asymmetric formatting improves retrieval.
    """

    def __init__(self, client: genai.Client | None = None, model: str = GEMINI_EMBEDDING_MODEL):
        self._client = client or genai.Client()  # Vertex AI (ADC) or API key, from env vars
        self._model = model
        self._config = types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIMS)

    async def embed_documents(self, documents: list[tuple[str, str]]) -> list[list[float]]:
        # One request per document, run concurrently. gemini-embedding-2 is multimodal: a LIST
        # of strings is read as the parts of ONE content and returns ONE vector, not one each.
        # (Caught by zip(strict=True) in store.py.)
        return list(
            await asyncio.gather(
                *(self._embed_one(f"title: {title} | text: {text}") for title, text in documents)
            )
        )

    async def embed_query(self, query: str) -> list[float]:
        return await self._embed_one(f"task: search result | query: {query}")

    async def _embed_one(self, text: str) -> list[float]:
        response = await self._client.aio.models.embed_content(
            model=self._model, contents=text, config=self._config
        )
        embeddings = response.embeddings or []
        if len(embeddings) != 1:
            raise RuntimeError(f"expected 1 embedding, got {len(embeddings)}")
        return list(embeddings[0].values or [])


class FakeEmbedder:
    """Deterministic bag-of-words hashing into 768 dims. Shared words -> higher cosine
    similarity, which is enough to test the plumbing. NOT semantic: never use in production."""

    async def embed_documents(self, documents: list[tuple[str, str]]) -> list[list[float]]:
        return [_hash_vector(f"{title} {text}") for title, text in documents]

    async def embed_query(self, query: str) -> list[float]:
        return _hash_vector(query)


def _hash_vector(text: str) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMS
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        bucket = int(hashlib.sha256(word.encode()).hexdigest(), 16) % EMBEDDING_DIMS
        vector[bucket] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]
