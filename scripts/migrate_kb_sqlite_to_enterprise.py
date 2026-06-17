#!/usr/bin/env python3
"""Migrate current SQLite PRD unit KB data into PostgreSQL + Qdrant.

This script reads the existing SQLite unit KB and imports each document into the
enterprise store through the same cleaned JSON import path used by the app.

Required enterprise env:
  KB_POSTGRES_DSN=postgresql://...
  KB_QDRANT_URL=http://localhost:6333
  KB_STORAGE_MODE is ignored by this script; enterprise store is used directly.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass

from services.kb.embedding_provider import HashingEmbeddingProvider, SentenceTransformerEmbeddingProvider
from services.kb.prd_unit_vector_store import PRDUnitVectorStore
from services.kb.storage.enterprise_store import EnterprisePRDKnowledgeStore


DEFAULT_SQLITE_DB = "data/specrag.db"
DEFAULT_OUTPUT_DIR = "runtime/kb_migrations/sqlite_to_enterprise"
DEFAULT_EMBEDDING_MODEL = "runtime/models/qwen3-embedding-0.6b"


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate SQLite PRD unit KB to enterprise storage")
    parser.add_argument("--sqlite-db", default=DEFAULT_SQLITE_DB)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--doc-id", action="append", help="Only migrate this doc_id. Can be passed multiple times.")
    parser.add_argument("--rebuild", action="store_true", help="Force rebuild documents and vectors in enterprise storage.")
    parser.add_argument(
        "--embedding-provider",
        choices=["sentence", "hash"],
        default="sentence",
        help="Use sentence for real semantic vectors, hash for quick connectivity testing.",
    )
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    args = parser.parse_args()

    sqlite_store = PRDUnitVectorStore(
        db_path=args.sqlite_db,
        embedding_provider=HashingEmbeddingProvider(),
    )
    docs = sqlite_store.list_documents()
    if args.doc_id:
        allowed = set(args.doc_id)
        docs = [doc for doc in docs if doc.get("doc_id") in allowed]

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    enterprise_store = EnterprisePRDKnowledgeStore(
        embedding_provider=_embedding_provider(args.embedding_provider, args.embedding_model),
    )

    results = []
    for doc in docs:
        doc_id = str(doc.get("doc_id") or "").strip()
        if not doc_id:
            continue
        units = sqlite_store.get_units(doc_id)
        payload = _build_cleaned_payload(doc, units)
        export_path = output_dir / f"{_safe_name(doc_id)}.with_hints.json"
        export_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        result = enterprise_store.import_cleaned_json(str(export_path), rebuild=args.rebuild)
        feedback_result = _migrate_feedback_hints(sqlite_store, enterprise_store, doc_id)
        result["source_doc_id"] = doc_id
        result["export_path"] = str(export_path)
        result["feedback_hints"] = feedback_result
        results.append(result)

    print(json.dumps({
        "status": "ok",
        "sqlite_db": args.sqlite_db,
        "migrated_documents": len(results),
        "results": results,
    }, ensure_ascii=False, indent=2))
    return 0


def _embedding_provider(provider: str, model_path: str):
    if provider == "hash":
        return HashingEmbeddingProvider()
    return SentenceTransformerEmbeddingProvider(model_path=model_path, query_prompt_name="query")


def _build_cleaned_payload(doc: Dict[str, Any], units: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "schema_version": doc.get("schema_version") or "kb_prd_units_v1",
        "document": {
            "doc_id": doc.get("doc_id"),
            "title": doc.get("title") or doc.get("doc_id"),
            "product": doc.get("product") or "unknown",
            "version": doc.get("version") or "unknown",
            "module": doc.get("module") or "",
            "summary": doc.get("summary") or "",
            "source_type": "sqlite_migration",
            "source_uri": doc.get("source_json_path") or "",
        },
        "units": units,
        "warnings": [],
    }


def _migrate_feedback_hints(
    sqlite_store: PRDUnitVectorStore,
    enterprise_store: EnterprisePRDKnowledgeStore,
    doc_id: str,
) -> Dict[str, Any]:
    migrated = 0
    errors = []
    for hint in sqlite_store.list_feedback_hints(doc_id):
        try:
            enterprise_store.add_feedback_hint(
                str(hint.get("doc_id") or doc_id),
                str(hint.get("unit_id") or ""),
                str(hint.get("query_text") or ""),
            )
            migrated += 1
        except Exception as exc:
            errors.append({
                "feedback_id": hint.get("feedback_id"),
                "unit_id": hint.get("unit_id"),
                "error": str(exc),
            })
    return {"migrated": migrated, "errors": errors}


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value) or "document"


if __name__ == "__main__":
    raise SystemExit(main())
