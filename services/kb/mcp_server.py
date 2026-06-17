"""MCP server for SpecRAG."""

from __future__ import annotations

import os
import json
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

from services.kb.storage import create_kb_store


DEFAULT_DB_PATH = os.environ.get("PRD_UNIT_KB_DB", "data/specrag.db")
DEFAULT_MODEL_PATH = os.environ.get("PRD_UNIT_EMBEDDING_MODEL", "runtime/models/qwen3-embedding-0.6b")
DEFAULT_EMBEDDING_PROVIDER = os.environ.get("PRD_UNIT_EMBEDDING_PROVIDER", "sentence")
_KB_CACHE: Dict[tuple[str, ...], Any] = {}


def create_mcp_server() -> FastMCP:
    server = FastMCP(
        name="specrag",
        instructions=(
            "SpecRAG MCP. Use retrieval tools to find knowledge units from business documents, "
            "then judge answerability and synthesize answers strictly from evidence."
        ),
    )

    @server.tool()
    def list_documents(db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
        """List all imported PRD documents."""
        kb = _unit_kb(db_path)
        return {"documents": kb.list_documents(), "db_path": db_path}

    @server.tool()
    def get_document(doc_id: str, db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
        """Get one PRD document with document-level metadata."""
        kb = _unit_kb(db_path)
        return {"document": kb.get_document(doc_id), "db_path": db_path}

    @server.tool()
    def get_units(doc_id: str, db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
        """Get all units of one PRD document."""
        kb = _unit_kb(db_path)
        return {"doc_id": doc_id, "units": [_compact_unit(unit) for unit in kb.get_units(doc_id)], "db_path": db_path}

    @server.tool()
    def get_unit(doc_id: str, unit_id: str, db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
        """Get one requirement unit by doc_id and unit_id."""
        kb = _unit_kb(db_path)
        return {"unit": _compact_unit(kb.get_unit(doc_id, unit_id)), "db_path": db_path}

    @server.tool()
    def list_feedback_hints(doc_id: str, unit_id: Optional[str] = None, db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
        """List feedback query hints for a document or a specific unit."""
        kb = _unit_kb(db_path)
        return {
            "doc_id": doc_id,
            "unit_id": unit_id,
            "hints": kb.list_feedback_hints(doc_id, unit_id=unit_id),
            "db_path": db_path,
        }

    @server.tool()
    def search_units(
        query: str,
        top_k: int = 5,
        product: Optional[str] = None,
        version: Optional[str] = None,
        module: Optional[str] = None,
        vector_types: Optional[List[str]] = None,
        candidate_k: Optional[int] = None,
        evidence_k: Optional[int] = None,
        min_score: Optional[float] = None,
        db_path: str = DEFAULT_DB_PATH,
    ) -> Dict[str, Any]:
        """Search PRD units by vector similarity."""
        kb = _unit_kb(db_path)
        results = kb.search(
            query=query,
            top_k=top_k,
            product=product,
            version=version,
            vector_types=vector_types,
            candidate_k=candidate_k,
            evidence_k=evidence_k,
            module=module,
            min_score=min_score,
        )
        return {
            "query": query,
            "results": [_compact_search_result(item) for item in results],
            "retrieval_meta": {
                "top_k": top_k,
                "candidate_k": candidate_k,
                "evidence_k": evidence_k,
                "returned_count": len(results),
                "vector_types": vector_types,
                "product": product,
                "version": version,
                "module": module,
                "min_score": min_score,
            },
            "db_path": db_path,
        }

    @server.tool()
    def expand_search(
        query: str,
        missing_aspects: Optional[List[str]] = None,
        exclude_unit_ids: Optional[List[str]] = None,
        top_k: int = 12,
        product: Optional[str] = None,
        version: Optional[str] = None,
        module: Optional[str] = None,
        db_path: str = DEFAULT_DB_PATH,
    ) -> Dict[str, Any]:
        """Run a broader search to gather more diverse candidate units."""
        kb = _unit_kb(db_path)
        normalized_missing_aspects = _normalize_string_list(missing_aspects)
        normalized_exclude_unit_ids = _normalize_string_list(exclude_unit_ids)
        variants = _expand_queries(query, normalized_missing_aspects)
        seen: set[str] = {_normalize_unit_id(unit_id) for unit_id in normalized_exclude_unit_ids if _normalize_unit_id(unit_id)}
        collected: List[Dict[str, Any]] = []
        for variant in variants:
            results = kb.search(
                query=variant,
                top_k=max(top_k, 5),
                product=product,
                version=version,
                module=module,
                vector_types=["body", "agent_hint_bundle", "feedback_hint"],
            )
            for item in results:
                unit_id = _normalize_unit_id(item.get("unit_id") or "")
                if unit_id and unit_id not in seen:
                    seen.add(unit_id)
                    collected.append(item)
        collected.sort(key=lambda item: item.get("score", 0.0), reverse=True)
        return {
            "query": query,
            "variants": variants,
            "results": [_compact_search_result(item) for item in collected[:top_k]],
            "retrieval_meta": {
                "top_k": top_k,
                "returned_count": min(len(collected), top_k),
                "missing_aspects": normalized_missing_aspects,
                "exclude_unit_ids": normalized_exclude_unit_ids,
            },
            "db_path": db_path,
        }

    @server.tool()
    def judge_answerability(query: str, unit_refs: List[Dict[str, str]], db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
        """Judge whether retrieved units are sufficient to answer the query."""
        kb = _unit_kb(db_path)
        units = _load_units(kb, unit_refs)
        return {
            "query": query,
            "answerability": kb.answerability_gate.judge(query, units),
            "db_path": db_path,
        }

    @server.tool()
    def synthesize_answer(
        query: str,
        unit_refs: List[Dict[str, str]],
        answerability: Dict[str, Any],
        db_path: str = DEFAULT_DB_PATH,
    ) -> Dict[str, Any]:
        """Synthesize a concise answer from supporting units."""
        kb = _unit_kb(db_path)
        units = _load_units(kb, unit_refs)
        return {
            "query": query,
            "answer_synthesis": kb.answer_synthesizer.synthesize(query, units, answerability),
            "sources": [_source_from_unit_ref(unit_ref, unit) for unit_ref, unit in zip(unit_refs, units)],
            "db_path": db_path,
        }

    @server.tool()
    def ask(
        query: str,
        top_k: int = 5,
        product: Optional[str] = None,
        version: Optional[str] = None,
        db_path: str = DEFAULT_DB_PATH,
    ) -> Dict[str, Any]:
        """One-shot retrieval, judge, and synthesis pipeline."""
        kb = _unit_kb(db_path)
        return kb.ask(query, top_k=top_k, product=product, version=version)

    @server.tool()
    def stats(db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
        """Get knowledge-base statistics."""
        kb = _unit_kb(db_path)
        return {"stats": kb.stats(), "db_path": db_path}

    @server.tool()
    def import_cleaned_json(cleaned_json_path: str, rebuild: bool = False, db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
        """Import one cleaned PRD requirement-unit JSON into the vector KB."""
        kb = _unit_kb(db_path)
        return {
            "import_result": kb.import_cleaned_json(cleaned_json_path, rebuild=rebuild),
            "db_path": db_path,
        }

    @server.tool()
    def add_feedback_hint(doc_id: str, unit_id: str, query_text: str, db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
        """Add a user feedback query hint for one requirement unit."""
        kb = _unit_kb(db_path)
        return {
            "feedback": kb.add_feedback_hint(doc_id, unit_id, query_text),
            "db_path": db_path,
        }

    return server


def _unit_kb(db_path: str):
    provider_name = os.environ.get("PRD_UNIT_EMBEDDING_PROVIDER", DEFAULT_EMBEDDING_PROVIDER).strip().lower()
    model_path = os.environ.get("PRD_UNIT_EMBEDDING_MODEL", DEFAULT_MODEL_PATH).strip()
    judge_mode = os.environ.get("PRD_UNIT_JUDGE_MODE", "rule").strip().lower()
    cache_key = (
        os.environ.get("KB_STORAGE_MODE", "enterprise"),
        str(db_path),
        model_path,
        provider_name,
        judge_mode,
        os.environ.get("KB_POSTGRES_DSN", ""),
        os.environ.get("KB_QDRANT_URL", ""),
        os.environ.get("KB_QDRANT_COLLECTION", ""),
    )
    if cache_key in _KB_CACHE:
        return _KB_CACHE[cache_key]

    kb = create_kb_store(db_path=db_path, judge=judge_mode)
    _KB_CACHE[cache_key] = kb
    return kb


def _load_units(kb, unit_refs: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    units: List[Dict[str, Any]] = []
    for ref in unit_refs:
        doc_id = str((ref or {}).get("doc_id") or "").strip()
        unit_id = str((ref or {}).get("unit_id") or "").strip()
        if not doc_id or not unit_id:
            continue
        unit = kb.get_unit(doc_id, unit_id)
        unit["doc_id"] = doc_id
        unit["unit_id"] = unit_id
        units.append(unit)
    return units


def _compact_search_result(item: Dict[str, Any]) -> Dict[str, Any]:
    unit = item.get("unit") or {}
    return {
        "score": item.get("score"),
        "vector_type": item.get("vector_type"),
        "doc_id": item.get("doc_id"),
        "doc_title": item.get("doc_title"),
        "product": item.get("product"),
        "version": item.get("version"),
        "module": item.get("module"),
        "unit_id": item.get("unit_id") or unit.get("unit_id"),
        "unit_title": unit.get("title"),
        "unit": _compact_unit(unit),
    }


def _compact_unit(unit: Dict[str, Any]) -> Dict[str, Any]:
    source = unit.get("source") or {}
    return {
        "unit_id": unit.get("unit_id"),
        "title": unit.get("title"),
        "unit_type": unit.get("unit_type"),
        "scope": unit.get("scope"),
        "content": unit.get("content"),
        "rules": unit.get("rules") or [],
        "source": {
            "evidence": source.get("evidence"),
            "heading_path": source.get("heading_path"),
            "start_line": source.get("start_line"),
            "end_line": source.get("end_line"),
        },
    }


def _source_from_unit_ref(unit_ref: Dict[str, str], unit: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "doc_id": (unit_ref or {}).get("doc_id") or unit.get("doc_id"),
        "unit_id": (unit_ref or {}).get("unit_id") or unit.get("unit_id"),
        "unit_title": unit.get("title"),
    }


def _normalize_string_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item or "").strip()]
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item or "").strip()]
    return [text]


def _normalize_unit_id(value: Any) -> str:
    text = str(value or "").strip()
    if ":" in text:
        text = text.rsplit(":", 1)[-1]
    return text


def _expand_queries(query: str, missing_aspects: List[str]) -> List[str]:
    variants = [query]
    for aspect in missing_aspects[:5]:
        aspect_text = str(aspect).strip()
        if aspect_text:
            variants.append(f"{query} {aspect_text}")
    return list(dict.fromkeys(variants))
