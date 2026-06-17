"""Enterprise SpecRAG store backed by PostgreSQL and Qdrant."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.kb.embedding_provider import EmbeddingProvider
from services.kb.prd_answerability_gate import PRDAnswerabilityGate, LLMEvidenceSynthesizerGate
from services.kb.prd_unit_vector_store import (
    build_feedback_hint_text,
    build_unit_vector_payloads,
)

from .models import KBSearchFilter, KBSearchOptions
from .postgres_store import PostgresUnitRepository
from .qdrant_vector_store import QdrantVectorIndex


class EnterprisePRDKnowledgeStore:
    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider,
        answerability_gate: Optional[PRDAnswerabilityGate] = None,
        repository: Optional[PostgresUnitRepository] = None,
        vector_index: Optional[QdrantVectorIndex] = None,
    ):
        self.embedding_provider = embedding_provider
        self.answerability_gate = answerability_gate or PRDAnswerabilityGate()
        self.answer_synthesizer = LLMEvidenceSynthesizerGate()
        self.repository = repository or PostgresUnitRepository()
        self.vector_index = vector_index or QdrantVectorIndex()

    def import_cleaned_json(self, cleaned_json_path: str, *, rebuild: bool = False) -> Dict[str, Any]:
        path = Path(cleaned_json_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        document = data.get("document") or {}
        units = data.get("units") or []
        if not units:
            raise ValueError(f"No units found in {path}")

        doc_id = str(document.get("doc_id") or path.stem)
        if not document.get("doc_id"):
            document["doc_id"] = doc_id
            data["document"] = document
        tenant_id = str(document.get("tenant_id") or os.environ.get("KB_TENANT_ID") or "default")
        document["tenant_id"] = tenant_id
        content_hash = _content_hash(data)

        existing_hash = self.repository.get_document_hash(doc_id)
        if existing_hash == content_hash and not rebuild:
            return {
                "doc_id": doc_id,
                "status": "skipped",
                "unit_count": len(units),
                "vector_count": 0,
                "embedding_model": self.embedding_provider.model_name,
                "storage_mode": "enterprise",
            }

        if rebuild or (existing_hash and existing_hash != content_hash):
            self.vector_index.delete_document(doc_id, tenant_id=tenant_id)

        upsert_result = self.repository.upsert_document_with_units(data, str(path))
        vector_payloads: List[Dict[str, Any]] = []
        for unit in units:
            unit_id = str(unit.get("unit_id") or "")
            if not unit_id:
                continue
            unit_pk = f"{doc_id}:{unit_id}"
            vector_payloads.extend(build_unit_vector_payloads(data, unit, unit_pk=unit_pk, doc_id=doc_id))

        embeddings = self.embedding_provider.embed_texts([payload["embedding_text"] for payload in vector_payloads])
        qdrant_vectors = []
        embedding_records = []
        collection = self.vector_index.collection
        now_status = "active"
        document_product = str(document.get("product_id") or document.get("product") or "unknown")
        for payload, embedding in zip(vector_payloads, embeddings):
            unit = next((item for item in units if str(item.get("unit_id") or "") == payload["unit_id"]), {})
            unit_pk = payload["unit_pk"]
            point_key = _point_key(
                tenant_id=tenant_id,
                doc_id=doc_id,
                unit_id=payload["unit_id"],
                vector_type=payload["vector_type"],
                vector_index=payload["vector_index"],
                embedding_model=self.embedding_provider.model_name,
                embedding_version=self.embedding_provider.version,
            )
            embedding_text_hash = _content_hash(payload["embedding_text"])
            vector_hash = _content_hash({
                "unit_pk": unit_pk,
                "vector_type": payload["vector_type"],
                "vector_index": payload["vector_index"],
                "embedding_text": payload["embedding_text"],
            })
            qdrant_vectors.append({
                "point_id": point_key,
                "vector": embedding,
                "payload": {
                    "tenant_id": tenant_id,
                    "doc_id": doc_id,
                    "unit_pk": unit_pk,
                    "unit_id": payload["unit_id"],
                    "vector_type": payload["vector_type"],
                    "product_id": document_product,
                    "product": document_product,
                    "product_line": document.get("product_line") or document.get("product") or "",
                    "module": document.get("module") or "",
                    "version": document.get("version") or "unknown",
                    "version_time": document.get("version_time") or "",
                    "unit_type": unit.get("unit_type") or "",
                    "change_type": unit.get("change_type") or document.get("change_type") or "",
                    "status": now_status,
                    "acl_group_ids": document.get("acl_group_ids") or [],
                    "embedding_model": self.embedding_provider.model_name,
                    "embedding_version": self.embedding_provider.version,
                    "content_hash": vector_hash,
                },
            })
            embedding_records.append({
                "embedding_id": _content_hash(f"{collection}:{point_key}"),
                "tenant_id": tenant_id,
                "unit_pk": unit_pk,
                "doc_id": doc_id,
                "unit_id": payload["unit_id"],
                "vector_type": payload["vector_type"],
                "vector_index": payload["vector_index"],
                "embedding_model": self.embedding_provider.model_name,
                "embedding_version": self.embedding_provider.version,
                "qdrant_collection": collection,
                "qdrant_point_id": point_key,
                "embedding_text_hash": embedding_text_hash,
                "content_hash": vector_hash,
                "status": now_status,
            })

        qdrant_result = self.vector_index.upsert_vectors(qdrant_vectors)
        self.repository.replace_embedding_records(doc_id, embedding_records)
        return {
            "doc_id": doc_id,
            "status": "rebuilt" if existing_hash else "imported",
            "unit_count": upsert_result.get("unit_count", len(units)),
            "vector_count": len(qdrant_vectors),
            "embedding_model": self.embedding_provider.model_name,
            "storage_mode": "enterprise",
            "qdrant": qdrant_result,
        }

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        product: Optional[str] = None,
        version: Optional[str] = None,
        vector_types: Optional[List[str]] = None,
        candidate_k: Optional[int] = None,
        evidence_k: Optional[int] = None,
        module: Optional[str] = None,
        tenant_id: Optional[str] = None,
        min_score: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        options = KBSearchOptions(
            candidate_k=int(candidate_k or os.environ.get("KB_DEFAULT_CANDIDATE_K") or max(top_k * 5, 30)),
            evidence_k=int(evidence_k or top_k or os.environ.get("KB_DEFAULT_EVIDENCE_K") or 8),
            min_score=min_score if min_score is not None else _optional_float(os.environ.get("KB_SEARCH_MIN_SCORE")),
        )
        filters = KBSearchFilter(
            tenant_id=tenant_id or os.environ.get("KB_TENANT_ID") or "default",
            product_id=product,
            product=product,
            module=module,
            version=version,
            vector_types=vector_types,
        )
        query_vector = _embed_query(self.embedding_provider, query)
        hits = self.vector_index.search(query_vector, filters, options)
        pruned = _prune_hits(hits, evidence_k=options.evidence_k)
        unit_pks = [item["payload"].get("unit_pk") for item in pruned if item.get("payload", {}).get("unit_pk")]
        rows = self.repository.list_units_by_pks(unit_pks)
        row_by_pk = {row["unit_pk"]: row for row in rows}

        results = []
        for hit in pruned:
            payload = hit.get("payload") or {}
            unit_pk = payload.get("unit_pk")
            row = row_by_pk.get(unit_pk)
            if not row:
                continue
            unit = row.get("unit_json") or {}
            results.append({
                "score": hit.get("score"),
                "vector_type": payload.get("vector_type"),
                "vector_index": payload.get("vector_index") or 1,
                "unit_pk": unit_pk,
                "doc_id": row.get("doc_id") or payload.get("doc_id"),
                "unit_id": row.get("unit_id") or payload.get("unit_id"),
                "doc_title": row.get("doc_title"),
                "product": row.get("product") or payload.get("product_id"),
                "version": row.get("version") or payload.get("version"),
                "module": row.get("module") or payload.get("module"),
                "unit": unit,
            })
        return results

    def ask(self, question: str, *, top_k: int = 5, product: Optional[str] = None, version: Optional[str] = None) -> Dict[str, Any]:
        results = self.search(question, top_k=top_k, product=product, version=version)
        if not results:
            return {
                "question": question,
                "answerable": False,
                "answerability": {"should_answer": False, "reason": "no retrieved units", "intents": [], "missing_intents": [], "evidence_hits": []},
                "answer": "未找到明确的知识单元。",
                "sources": [],
            }
        units = [item["unit"] for item in results]
        answerability = self.answerability_gate.judge(question, units)
        if not answerability.get("should_answer"):
            return {
                "question": question,
                "answerable": False,
                "answerability": answerability,
                "answer": "当前知识单元中未明确说明该问题，不能仅根据相近内容推断答案。",
                "sources": self._source_payloads(results),
            }
        synthesis = self.answer_synthesizer.synthesize(question, units, answerability)
        answer = (synthesis.get("synthesized_answer") or "").strip()
        return {
            "question": question,
            "answerable": True,
            "answerability": answerability,
            "answer": answer or "已找到相关知识单元，但答案整合为空。",
            "answer_synthesis": synthesis,
            "sources": self._source_payloads(results),
        }

    def add_feedback_hint(self, doc_id: str, unit_id: str, query_text: str) -> Dict[str, Any]:
        result = self.repository.add_feedback_hint(doc_id, unit_id, query_text)
        unit = self.repository.get_unit(doc_id, unit_id)
        document = self.repository.get_document(doc_id)
        hint_text = build_feedback_hint_text(document, unit, query_text)
        embedding = self.embedding_provider.embed_texts([hint_text])[0]
        tenant_id = str(document.get("tenant_id") or os.environ.get("KB_TENANT_ID") or "default")
        point_key = _point_key(
            tenant_id=tenant_id,
            doc_id=doc_id,
            unit_id=unit_id,
            vector_type="feedback_hint",
            feedback_id=result.get("feedback_id"),
            embedding_model=self.embedding_provider.model_name,
            embedding_version=self.embedding_provider.version,
        )
        vector_hash = _content_hash(hint_text)
        self.vector_index.upsert_vectors([{
            "point_id": point_key,
            "vector": embedding,
            "payload": {
                "tenant_id": tenant_id,
                "doc_id": doc_id,
                "unit_pk": f"{doc_id}:{unit_id}",
                "unit_id": unit_id,
                "vector_type": "feedback_hint",
                "feedback_id": result.get("feedback_id"),
                "product_id": document.get("product") or "unknown",
                "product": document.get("product") or "unknown",
                "module": document.get("module") or "",
                "version": document.get("version") or "unknown",
                "status": "active",
                "embedding_model": self.embedding_provider.model_name,
                "embedding_version": self.embedding_provider.version,
                "content_hash": vector_hash,
            },
        }])
        self.repository.add_embedding_record({
            "embedding_id": _content_hash(f"{self.vector_index.collection}:{point_key}"),
            "tenant_id": tenant_id,
            "unit_pk": f"{doc_id}:{unit_id}",
            "doc_id": doc_id,
            "unit_id": unit_id,
            "vector_type": "feedback_hint",
            "vector_index": 1,
            "embedding_model": self.embedding_provider.model_name,
            "embedding_version": self.embedding_provider.version,
            "qdrant_collection": self.vector_index.collection,
            "qdrant_point_id": point_key,
            "embedding_text_hash": vector_hash,
            "content_hash": vector_hash,
            "status": "active",
        })
        result["vector_id"] = point_key
        return result

    def list_feedback_hints(self, doc_id: str, unit_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.repository.list_feedback_hints(doc_id, unit_id=unit_id)

    def stats(self) -> Dict[str, Any]:
        stats = self.repository.stats()
        stats["storage_mode"] = "enterprise"
        stats["qdrant_collection"] = self.vector_index.collection
        return stats

    def list_documents(self) -> List[Dict[str, Any]]:
        return self.repository.list_documents()

    def get_document(self, doc_id: str) -> Dict[str, Any]:
        return self.repository.get_document(doc_id)

    def get_units(self, doc_id: str) -> List[Dict[str, Any]]:
        return self.repository.get_units(doc_id)

    def get_unit(self, doc_id: str, unit_id: str) -> Dict[str, Any]:
        return self.repository.get_unit(doc_id, unit_id)

    @staticmethod
    def _source_payloads(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        sources = []
        for item in results:
            unit = item.get("unit") or {}
            source = unit.get("source") or {}
            sources.append({
                "doc_id": item.get("doc_id"),
                "doc_title": item.get("doc_title"),
                "version": item.get("version"),
                "unit_id": item.get("unit_id"),
                "unit_title": unit.get("title"),
                "heading_path": source.get("heading_path"),
                "score": item.get("score"),
                "vector_type": item.get("vector_type"),
                "start_line": source.get("start_line"),
                "end_line": source.get("end_line"),
                "evidence": source.get("evidence"),
            })
        return sources


def _embed_query(provider: EmbeddingProvider, query: str) -> List[float]:
    if hasattr(provider, "embed_query"):
        return provider.embed_query(query)  # type: ignore[attr-defined]
    return provider.embed_texts([query])[0]


def _prune_hits(hits: List[Dict[str, Any]], *, evidence_k: int) -> List[Dict[str, Any]]:
    best_by_unit: Dict[str, Dict[str, Any]] = {}
    for hit in hits:
        payload = hit.get("payload") or {}
        unit_pk = str(payload.get("unit_pk") or "")
        if not unit_pk:
            continue
        current = best_by_unit.get(unit_pk)
        if current is None or float(hit.get("score") or 0) > float(current.get("score") or 0):
            best_by_unit[unit_pk] = hit
    ranked = list(best_by_unit.values())
    ranked.sort(key=lambda item: (float(item.get("score") or 0), _vector_priority((item.get("payload") or {}).get("vector_type"))), reverse=True)
    return ranked[:max(1, evidence_k)]


def _vector_priority(vector_type: Any) -> int:
    order = {"body": 3, "agent_hint_bundle": 2, "feedback_hint": 1}
    return order.get(str(vector_type or ""), 0)


def _optional_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _point_key(**parts: Any) -> str:
    return ":".join(str(value or "") for value in parts.values())


def _content_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
