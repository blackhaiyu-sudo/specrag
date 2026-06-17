"""Shared storage models for SpecRAG implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class KBSearchFilter:
    tenant_id: str = "default"
    product_id: Optional[str] = None
    product: Optional[str] = None
    module: Optional[str] = None
    version: Optional[str] = None
    status: str = "active"
    vector_types: Optional[List[str]] = None
    acl_group_ids: Optional[List[str]] = None


@dataclass
class KBSearchOptions:
    candidate_k: int = 50
    evidence_k: int = 8
    min_score: Optional[float] = None
    include_unit: bool = True


@dataclass
class KBVectorHit:
    score: float
    point_id: str
    payload: Dict[str, Any]
