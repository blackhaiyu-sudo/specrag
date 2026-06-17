"""Embedding providers for the lightweight SpecRAG knowledge base.

The default provider is intentionally local and deterministic so the first
knowledge-base loop can run without an external embedding service. It is a
replaceable adapter, not the final semantic embedding strategy.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
import re
from typing import Iterable, List


class EmbeddingProvider:
    """Small interface used by the KB services."""

    model_name = "base"
    version = "1"

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError


class HashingEmbeddingProvider(EmbeddingProvider):
    """Deterministic local feature-hashing embedding.

    This is not a replacement for a real semantic embedding model. It gives us a
    stable vector store and cosine-search path for development and tests. The
    tokenization intentionally includes Chinese character n-grams because most
    historical PRDs are Chinese business documents.
    """

    model_name = "local-hashing-char-ngram"
    version = "v1"

    def __init__(self, dimensions: int = 768):
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self.dimensions = dimensions

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return [self._embed(text) for text in texts]

    def _embed(self, text: str) -> List[float]:
        vector = [0.0] * self.dimensions
        for token in _tokens(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "big")
            index = value % self.dimensions
            sign = -1.0 if value & 1 else 1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if not norm:
            return vector
        return [round(value / norm, 8) for value in vector]


class SentenceTransformerEmbeddingProvider(EmbeddingProvider):
    """Local sentence-transformers embedding provider."""

    version = "v1"

    def __init__(
        self,
        model_path: str = "runtime/models/qwen3-embedding-0.6b",
        *,
        query_prompt_name: str = "query",
        normalize_embeddings: bool = True,
        batch_size: int = 1,
    ):
        self.model_path = str(model_path)
        self.model_name = Path(model_path).name or str(model_path)
        self.query_prompt_name = query_prompt_name
        self.normalize_embeddings = normalize_embeddings
        self.batch_size = max(1, batch_size)
        self._model = None

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        vectors = self._load_model().encode(
            texts,
            normalize_embeddings=self.normalize_embeddings,
            show_progress_bar=False,
            batch_size=self.batch_size,
        )
        return [self._vector_to_list(vector) for vector in vectors]

    def embed_query(self, text: str) -> List[float]:
        kwargs = {"prompt_name": self.query_prompt_name} if self.query_prompt_name else {}
        vectors = self._load_model().encode(
            [text],
            normalize_embeddings=self.normalize_embeddings,
            show_progress_bar=False,
            batch_size=self.batch_size,
            **kwargs,
        )
        return self._vector_to_list(vectors[0])

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_path)
        return self._model

    @staticmethod
    def _vector_to_list(vector) -> List[float]:
        if hasattr(vector, "tolist"):
            return [float(value) for value in vector.tolist()]
        return [float(value) for value in vector]


def cosine_similarity(left: List[float], right: List[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def _tokens(text: str) -> Iterable[str]:
    normalized = re.sub(r"\s+", " ", str(text or "").lower()).strip()
    if not normalized:
        return []

    tokens: List[str] = []
    tokens.extend(re.findall(r"[a-z0-9_./#-]{2,}", normalized))

    cjk_runs = re.findall(r"[\u4e00-\u9fff]+", normalized)
    for run in cjk_runs:
        tokens.extend(_ngrams(run, 1))
        tokens.extend(_ngrams(run, 2))
        tokens.extend(_ngrams(run, 3))

    mixed = re.sub(r"\s+", "", normalized)
    if len(mixed) <= 80:
        tokens.extend(_ngrams(mixed, 4))
    else:
        for run in re.split(r"[，。；：、,.!！?？\s]+", mixed):
            if run:
                tokens.extend(_ngrams(run, 4))

    return tokens


def _ngrams(text: str, size: int) -> List[str]:
    if len(text) < size:
        return []
    return [text[index:index + size] for index in range(0, len(text) - size + 1)]
