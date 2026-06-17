"""Factory for selecting the SpecRAG storage backend."""

from __future__ import annotations

import os
from typing import Optional

from services.kb.embedding_provider import (
    EmbeddingProvider,
    HashingEmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
)
from services.kb.prd_answerability_gate import LLMEvidenceJudgeGate, PRDAnswerabilityGate


DEFAULT_DB_PATH = "data/specrag.db"
DEFAULT_MODEL_PATH = "runtime/models/qwen3-embedding-0.6b"


def create_kb_store(
    *,
    mode: Optional[str] = None,
    db_path: Optional[str] = None,
    embedding_provider: Optional[EmbeddingProvider] = None,
    judge: str = "rule",
    lightweight: bool = False,
):
    """Create the configured SpecRAG store.

    Storage modes:
    - enterprise: PostgreSQL facts + Qdrant vectors.
    - sqlite: local SQLite implementation for development and demos.
    """

    storage_mode = (mode or os.environ.get("KB_STORAGE_MODE") or "enterprise").strip().lower()
    provider = embedding_provider or _embedding_provider(lightweight=lightweight)
    answerability_gate = LLMEvidenceJudgeGate() if str(judge or "rule").lower() == "llm" else PRDAnswerabilityGate()

    if storage_mode in {"sqlite", "local"}:
        from services.kb.prd_unit_vector_store import PRDUnitVectorStore

        return PRDUnitVectorStore(
            db_path=db_path or os.environ.get("PRD_UNIT_KB_DB", DEFAULT_DB_PATH),
            embedding_provider=provider,
            answerability_gate=answerability_gate,
        )

    if storage_mode in {"enterprise", "postgres_qdrant", "postgres+qdrant"}:
        from .enterprise_store import EnterprisePRDKnowledgeStore

        return EnterprisePRDKnowledgeStore(
            embedding_provider=provider,
            answerability_gate=answerability_gate,
        )

    raise ValueError(f"Unsupported KB_STORAGE_MODE: {storage_mode}")


def _embedding_provider(*, lightweight: bool = False) -> EmbeddingProvider:
    provider_name = os.environ.get("PRD_UNIT_EMBEDDING_PROVIDER", "sentence").strip().lower()
    if lightweight or provider_name in {"hash", "hashing", "local-hash", "local-hashing"}:
        return HashingEmbeddingProvider()
    return SentenceTransformerEmbeddingProvider(
        model_path=os.environ.get("PRD_UNIT_EMBEDDING_MODEL", DEFAULT_MODEL_PATH),
        query_prompt_name="query",
    )
