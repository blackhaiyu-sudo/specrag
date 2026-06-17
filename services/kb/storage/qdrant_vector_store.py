"""Qdrant vector index for PRD requirement units."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from .models import KBSearchFilter, KBSearchOptions


class QdrantVectorIndex:
    def __init__(
        self,
        *,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        collection: Optional[str] = None,
    ):
        self.url = url or os.environ.get("KB_QDRANT_URL") or "http://localhost:6333"
        self.api_key = api_key if api_key is not None else os.environ.get("KB_QDRANT_API_KEY")
        self.collection = collection or os.environ.get("KB_QDRANT_COLLECTION") or "specrag_units"
        self._client = None

    @property
    def client(self):
        if self._client is None:
            try:
                from qdrant_client import QdrantClient
            except ImportError as exc:
                raise RuntimeError("qdrant-client is required for KB_STORAGE_MODE=enterprise") from exc
            self._client = QdrantClient(url=self.url, api_key=self.api_key or None)
        return self._client

    def ensure_collection(self, vector_size: int) -> None:
        from qdrant_client.models import Distance, VectorParams

        try:
            self.client.get_collection(self.collection)
            return
        except Exception:
            pass
        self.client.create_collection(
            collection_name=self.collection,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )
        self.create_payload_indexes()

    def create_payload_indexes(self) -> None:
        from qdrant_client.models import PayloadSchemaType

        schema = {
            "tenant_id": PayloadSchemaType.KEYWORD,
            "doc_id": PayloadSchemaType.KEYWORD,
            "unit_pk": PayloadSchemaType.KEYWORD,
            "unit_id": PayloadSchemaType.KEYWORD,
            "vector_type": PayloadSchemaType.KEYWORD,
            "product_id": PayloadSchemaType.KEYWORD,
            "product": PayloadSchemaType.KEYWORD,
            "module": PayloadSchemaType.KEYWORD,
            "version": PayloadSchemaType.KEYWORD,
            "status": PayloadSchemaType.KEYWORD,
            "unit_type": PayloadSchemaType.KEYWORD,
            "change_type": PayloadSchemaType.KEYWORD,
            "acl_group_ids": PayloadSchemaType.KEYWORD,
        }
        for field_name, field_schema in schema.items():
            try:
                self.client.create_payload_index(
                    collection_name=self.collection,
                    field_name=field_name,
                    field_schema=field_schema,
                )
            except Exception:
                # Existing indexes or older Qdrant versions should not block startup.
                continue

    def delete_document(self, doc_id: str, tenant_id: str = "default") -> None:
        from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

        try:
            self.client.get_collection(self.collection)
        except Exception:
            return

        query_filter = Filter(
            must=[
                FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id)),
                FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
            ]
        )
        self.client.delete(
            collection_name=self.collection,
            points_selector=FilterSelector(filter=query_filter),
        )

    def upsert_vectors(self, vectors: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not vectors:
            return {"upserted": 0, "collection": self.collection}
        from qdrant_client.models import PointStruct

        vector_size = len(vectors[0]["vector"])
        self.ensure_collection(vector_size)
        points = [
            PointStruct(
                id=_point_id(item["point_id"]),
                vector=item["vector"],
                payload=item["payload"],
            )
            for item in vectors
        ]
        self.client.upsert(collection_name=self.collection, points=points)
        return {"upserted": len(points), "collection": self.collection}

    def search(
        self,
        query_vector: List[float],
        filters: KBSearchFilter,
        options: KBSearchOptions,
    ) -> List[Dict[str, Any]]:
        query_filter = _build_filter(filters)
        limit = max(1, int(options.candidate_k or options.evidence_k or 8))
        if hasattr(self.client, "query_points"):
            response = self.client.query_points(
                collection_name=self.collection,
                query=query_vector,
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
            points = getattr(response, "points", response)
        else:
            points = self.client.search(
                collection_name=self.collection,
                query_vector=query_vector,
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
        hits = []
        for point in points:
            payload = dict(getattr(point, "payload", None) or {})
            score = float(getattr(point, "score", 0.0) or 0.0)
            if options.min_score is not None and score < options.min_score:
                continue
            hits.append({
                "score": round(score, 6),
                "point_id": str(getattr(point, "id", "")),
                "payload": payload,
            })
        return hits


def _build_filter(filters: KBSearchFilter):
    from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

    must = []
    if filters.tenant_id:
        must.append(FieldCondition(key="tenant_id", match=MatchValue(value=filters.tenant_id)))
    if filters.status:
        must.append(FieldCondition(key="status", match=MatchValue(value=filters.status)))
    if filters.product_id or filters.product:
        value = filters.product_id or filters.product
        must.append(FieldCondition(key="product_id", match=MatchValue(value=value)))
    if filters.module:
        must.append(FieldCondition(key="module", match=MatchValue(value=filters.module)))
    if filters.version:
        must.append(FieldCondition(key="version", match=MatchValue(value=filters.version)))
    if filters.vector_types:
        must.append(FieldCondition(key="vector_type", match=MatchAny(any=filters.vector_types)))
    if filters.acl_group_ids:
        must.append(FieldCondition(key="acl_group_ids", match=MatchAny(any=filters.acl_group_ids)))
    return Filter(must=must)


def _point_id(value: str) -> int:
    import hashlib

    text = str(value)
    # Qdrant accepts UUIDs or unsigned integers for point ids across all versions.
    # Use a deterministic integer to avoid depending on newer string-id support.
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)
